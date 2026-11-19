import json
from copy import deepcopy
from fractions import Fraction

import pending_examples
import pending_workflow
from cycles.counting import Cycle
from exchange.admission import receive
from reports.publication import publish, publish_pending
from reports.readback import read_pending
from segments.issue import issue_pending
from segments.manifest import IssueRegister
from segments.ranges import SegmentRange
from tests import LabTestCase
from trial.freeze import freeze, freeze_pending
from trial.observations import Observation
from trial.plan import TrialPlan
from trial.revisions import RevisionStore

HALF = Fraction(1, 2)
FULL = Fraction(1)


class PendingTests(LabTestCase):
    def freeze_pending_values(self, loads, *, trial_id='test-trial', first=1):
        plan = TrialPlan(trial_id, first, first + len(loads) - 1)
        observations = (Observation(slot, load) for slot, load in enumerate(loads, first))
        return freeze_pending(self.revisions, plan, observations)

    def issue_pending_range(self, revision_id, bounds):
        return issue_pending(self.revisions, self.register, revision_id, SegmentRange(*bounds))

    def intake_pending(self, revision_id, bounds):
        return [
            receive(self.admissions, self.issue_pending_range(revision_id, span).to_wire()).local_id
            for span in bounds
        ]

    def pending_counts(self):
        return tuple(
            self.review.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in ('pending_reports', 'pending_report_references', 'pending_report_receipts')
        )

    def test_freeze_pending_validation(self):
        plan = TrialPlan('test-trial', 1, 2)
        bad_loads = (
            ('0.5', '1/2'),  # same rational value twice
            (1,),  # too few candidates
            (1, 2, 3, 4),  # too many candidates
            (1, 'noise'),
            (1, True),
            (1, 0.1),
            [1, 2],  # a list is not a candidate tuple
        )
        for load in bad_loads:
            with self.subTest(load=load):
                with self.assertRaisesRegex(ValueError, 'INVALID_LOAD'):
                    freeze_pending(self.revisions, plan, [Observation(1, load), Observation(2, 0)])
        with self.assertRaisesRegex(ValueError, 'INVALID_LOAD'):
            freeze(self.revisions, plan, [Observation(1, (1, 2)), Observation(2, 0)])
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_SLOT'):
            freeze_pending(self.revisions, plan, [Observation(1, (1, 2)), Observation(1, 0)])
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_OBSERVATIONS'):
            freeze_pending(self.revisions, plan, [Observation(1, (1, 2))])
        with self.assertRaisesRegex(ValueError, 'OBSERVATION_BOUNDS'):
            freeze_pending(self.revisions, plan, [Observation(1, (1, 2)), Observation(3, 0)])
        self.assertEqual(self.source_counts(), (0, 0))

    def test_pending_limit_at_freeze(self):
        plan = TrialPlan('test-trial', 1, 9)
        with self.assertRaisesRegex(ValueError, 'PENDING_LIMIT'):
            freeze_pending(self.revisions, plan, [Observation(slot, (0, 1)) for slot in range(1, 10)])
        self.assertEqual(self.source_counts(), (0, 0))
        revision = freeze_pending(
            self.revisions, TrialPlan('test-trial', 1, 8),
            [Observation(slot, (0, 1)) for slot in range(1, 9)],
        )
        self.assertEqual(self.source_counts(), (1, 0))
        frozen = self.revisions.get_pending(revision)
        self.assertEqual(frozen.observations[3], Observation(4, (Fraction(0), Fraction(1))))

    def test_get_pending_roundtrip(self):
        revision = self.freeze_pending_values([0, ('0.5', '1/3'), None, '1/2'])
        frozen = self.revisions.get_pending(revision)
        self.assertEqual(frozen.observations, (
            Observation(1, Fraction(0)),
            Observation(2, (Fraction(1, 2), Fraction(1, 3))),
            Observation(3, None),
            Observation(4, Fraction(1, 2)),
        ))
        partial = self.revisions.get_pending(revision, first=2, last=3)
        self.assertEqual(partial.observations, (
            Observation(2, (Fraction(1, 2), Fraction(1, 3))), Observation(3, None),
        ))
        with self.assertRaisesRegex(ValueError, 'SEGMENT_BOUNDS'):
            self.revisions.get_pending(revision, first=0, last=3)
        with self.assertRaisesRegex(LookupError, 'REVISION_NOT_FOUND'):
            self.revisions.get_pending('unknown-revision')

    def test_pending_segment_elision(self):
        revision = self.freeze_pending_values([0, '1/2', 2, (0, 3), 6])
        segment = self.issue_pending_range(revision, (1, 5))
        self.assertEqual(segment.manifest.version, 2)
        payload = segment.payload
        self.assertEqual(dict(payload.determined), {1: Fraction(0), 3: Fraction(2), 5: Fraction(6)})
        self.assertEqual(payload.elided, (2,))
        self.assertEqual(dict(payload.pending), {4: (Fraction(0), Fraction(3))})
        self.assertEqual(payload.missing, ())
        self.assertNotIn('1/2', json.dumps(segment.to_wire()))
        again = self.issue_pending_range(revision, (1, 5))
        self.assertEqual(again, segment)
        self.assertEqual(self.source_counts(), (1, 1))
        # A boundary slot keeps its exact reading: the triple is not inside one segment.
        boundary = self.issue_pending_range(revision, (2, 2))
        self.assertEqual(dict(boundary.payload.determined), {2: Fraction(1, 2)})
        self.assertEqual(boundary.payload.elided, ())
        # The turn at slot 3 with amplitude 2 is derivable when slot 4 reads 0.
        ids = [receive(self.admissions, segment.to_wire()).local_id]
        report = publish_pending(self.admissions, self.catalog, revision, ids)
        self.assertIn(Cycle(3, 4, Fraction(2), HALF), report.possible)

    def test_elision_chain_and_plain_runs(self):
        revision = self.freeze_pending_values([0, 1, 2, 3, 6])
        segment = self.issue_pending_range(revision, (1, 5))
        self.assertEqual(segment.payload.elided, (2, 3, 4))
        self.assertEqual(dict(segment.payload.determined), {1: Fraction(0), 5: Fraction(6)})
        for values in ([0, 1, 1], [0, 2, 1], [0, 0, 1]):
            with self.subTest(values=values):
                other = self.freeze_pending_values(values)
                piece = self.issue_pending_range(other, (1, 3))
                self.assertEqual(piece.payload.elided, ())

    def test_receive_pending(self):
        revision = self.freeze_pending_values([0, (1, 2, 5), 6])
        wire = self.issue_pending_range(revision, (1, 3)).to_wire()
        self.assertEqual(wire['version'], 2)
        receipt = receive(self.admissions, wire)
        self.assertEqual(receive(self.admissions, wire), receipt)
        equivalent = deepcopy(wire)
        equivalent['payload']['pending'][0][1][0] = '1.0'
        self.assertEqual(receive(self.admissions, equivalent), receipt)
        conflict = deepcopy(wire)
        conflict['payload']['pending'][0][1][0] = '3'
        with self.assertRaisesRegex(ValueError, 'SEGMENT_CONFLICT'):
            receive(self.admissions, conflict)
        with self.assertRaisesRegex(ValueError, 'SEGMENT_CONFLICT'):
            receive(self.admissions, dict(wire, source='another-station'))
        self.assertEqual(self.review.execute('SELECT COUNT(*) FROM admissions').fetchone()[0], 1)

    def test_bad_pending_envelopes(self):
        revision = self.freeze_pending_values([0, (1, 2), 6])
        wire = self.issue_pending_range(revision, (1, 3)).to_wire()
        receive(self.admissions, wire)

        def envelope(segment_id, payload):
            return {
                'version': 2, 'segment_id': segment_id, 'source': 'bench',
                'trial_id': 'test-trial', 'revision_id': revision,
                'plan': [1, 3], 'span': [1, 3], 'payload': payload,
            }

        cases = [
            # elided slot at the segment boundary
            envelope('bad-1', {'determined': [[2, '5'], [3, '6']], 'elided': [1], 'pending': [], 'missing': []}),
            # a single candidate
            envelope('bad-2', {'determined': [[1, '0'], [3, '6']], 'elided': [], 'pending': [[2, ['1']]], 'missing': []}),
            # duplicate candidates by rational value
            envelope('bad-3', {'determined': [[1, '0'], [3, '6']], 'elided': [], 'pending': [[2, ['1', '1.0']]], 'missing': []}),
            # a slot covered twice
            envelope('bad-4', {'determined': [[1, '0'], [2, '1'], [3, '6']], 'elided': [2], 'pending': [], 'missing': []}),
            # elided chain whose monotone bounds are equal
            envelope('bad-5', {'determined': [[1, '5'], [3, '5']], 'elided': [2], 'pending': [], 'missing': []}),
            # elided slot next to a pending slot
            envelope('bad-6', {'determined': [[1, '0']], 'elided': [2], 'pending': [[3, ['1', '2']]], 'missing': []}),
            # uncovered slot
            envelope('bad-7', {'determined': [[1, '0'], [3, '6']], 'elided': [], 'pending': [], 'missing': []}),
            # adjacent missing fragments
            envelope('bad-8', {'determined': [[3, '6']], 'elided': [], 'pending': [], 'missing': [[1, 1], [2, 2]]}),
            # pending payload in a version 1 envelope
            dict(wire, version=1),
        ]
        for bad in cases:
            with self.subTest(segment_id=bad['segment_id']):
                with self.assertRaisesRegex(ValueError, 'INVALID_ENVELOPE'):
                    receive(self.admissions, bad)
        self.assertEqual(self.review.execute('SELECT COUNT(*) FROM admissions').fetchone()[0], 1)

    def test_publish_pending_fork(self):
        for cuts in pending_examples.FORK_CUTS:
            with self.subTest(cuts=cuts):
                revision = self.freeze_pending_values(list(pending_examples.FORK))
                ids = self.intake_pending(revision, cuts)
                report = publish_pending(self.admissions, self.catalog, revision, ids + ids[:1])
                self.assertEqual(report.possible, pending_examples.FORK_POSSIBLE)
                self.assertEqual(report.certain, pending_examples.FORK_CERTAIN)
                self.assertEqual(tuple((ref.first, ref.last) for ref in report.references), cuts)
                self.assertEqual(read_pending(self.catalog, report.report_id), report)

    def test_publish_pending_seam(self):
        expected_possible = (
            Cycle(1, 5, Fraction(6), HALF), Cycle(2, 4, Fraction(3), FULL),
            Cycle(3, 4, Fraction(4), FULL), Cycle(7, 8, Fraction(3), HALF),
        )
        expected_certain = (Cycle(1, 5, Fraction(6), HALF), Cycle(7, 8, Fraction(3), HALF))
        for cuts in pending_examples.SEAM_CUTS:
            with self.subTest(cuts=cuts):
                revision = self.freeze_pending_values(list(pending_examples.SEAM))
                ids = self.intake_pending(revision, cuts)
                report = publish_pending(self.admissions, self.catalog, revision, ids)
                self.assertEqual(report.possible, expected_possible)
                self.assertEqual(report.certain, expected_certain)

    def test_pending_query(self):
        revision = self.freeze_pending_values(list(pending_examples.FORK))
        ids = self.intake_pending(revision, [(1, 2), (3, 4)])
        report = publish_pending(
            self.admissions, self.catalog, revision, ids,
            query=(pending_examples.RANGE_THREE, pending_examples.RANGE_FOUR),
        )
        self.assertEqual(report.query, (pending_examples.RANGE_THREE, pending_examples.RANGE_FOUR))
        self.assertFalse(report.cooccurs)
        self.assertIsNone(report.witness)
        report = publish_pending(
            self.admissions, self.catalog, revision, ids,
            query=(pending_examples.REMAINDER, pending_examples.RANGE_FOUR),
        )
        self.assertTrue(report.cooccurs)
        self.assertEqual(report.witness, ((3, Fraction(1)),))
        report = publish_pending(self.admissions, self.catalog, revision, ids)
        self.assertIsNone(report.query)
        self.assertIsNone(report.cooccurs)
        self.assertIsNone(report.witness)

    def test_witness_covers_all_pending_slots(self):
        revision = self.freeze_pending_values([0, (1, 2), 6, (0, 3), 5])
        ids = self.intake_pending(revision, [(1, 5)])
        survey = publish_pending(self.admissions, self.catalog, revision, ids)
        self.assertTrue(survey.possible)
        report = publish_pending(
            self.admissions, self.catalog, revision, ids,
            query=(survey.possible[0], survey.possible[0]),
        )
        self.assertTrue(report.cooccurs)
        self.assertEqual(tuple(slot for slot, _ in report.witness), (2, 4))
        self.assertTrue(all(isinstance(load, Fraction) for _, load in report.witness))

    def test_invalid_query(self):
        revision = self.freeze_pending_values(list(pending_examples.FORK))
        ids = self.intake_pending(revision, [(1, 4)])
        remainder = pending_examples.REMAINDER
        bad = (
            (remainder,),
            (remainder, remainder, remainder),
            (Cycle(4, 4, Fraction(6), HALF), remainder),
            (Cycle(4, 1, Fraction(6), HALF), remainder),
            (Cycle(0, 4, Fraction(6), HALF), remainder),
            (Cycle(1, 5, Fraction(6), HALF), remainder),
            (Cycle(True, 4, Fraction(6), HALF), remainder),
            (Cycle(1, 4, Fraction(0), HALF), remainder),
            (Cycle(1, 4, Fraction(-2), HALF), remainder),
            (Cycle(1, 4, 6, HALF), remainder),
            (Cycle(1, 4, Fraction(6), Fraction(2)), remainder),
            (Cycle(1, 4, Fraction(6), Fraction(1, 3)), remainder),
            (Cycle(1, 4, Fraction(6), 1), remainder),
            (remainder, 'not-a-cycle'),
            'not-a-pair',
        )
        for query in bad:
            with self.subTest(query=query):
                with self.assertRaisesRegex(ValueError, 'INVALID_QUERY'):
                    publish_pending(self.admissions, self.catalog, revision, ids, query=query)
        self.assertEqual(self.pending_counts(), (0, 0, 0))

    def test_empty_pending_ledger(self):
        for loads in ([None, None], [0], [None, (1, 2), None], [5, 5, 5], [None, 2, None, None, 0, None]):
            with self.subTest(loads=loads):
                revision = self.freeze_pending_values(list(loads))
                ids = self.intake_pending(revision, [(1, len(loads))])
                report = publish_pending(self.admissions, self.catalog, revision, ids)
                self.assertEqual(report.possible, ())
                self.assertEqual(report.certain, ())
                self.assertEqual(read_pending(self.catalog, report.report_id), report)

    def test_pending_selection_rejections(self):
        revision = self.freeze_pending_values([0, (1, 2), 6])
        corrected = self.freeze_pending_values([0, (1, 2), 7])
        left, right = self.intake_pending(revision, [(1, 1), (3, 3)])
        (middle,) = self.intake_pending(revision, [(2, 2)])
        (overlap,) = self.intake_pending(revision, [(2, 3)])
        (foreign,) = self.intake_pending(corrected, [(3, 3)])
        (v1_piece,) = self.intake(revision, [(1, 1)])
        for ids, error in (
            ([left, right], 'COVERAGE_GAP'),
            ([left, middle, overlap], 'SEGMENT_OVERLAP'),
            ([left, middle, foreign], 'MIXED_REVISION'),
            ([left, middle, 'unknown-local'], 'UNKNOWN_SELECTION'),
            ([left, middle, v1_piece], 'MIXED_VERSION'),
            ([], 'COVERAGE_GAP'),
        ):
            with self.subTest(ids=ids, error=error):
                with self.assertRaisesRegex(ValueError, error):
                    publish_pending(self.admissions, self.catalog, revision, ids)
                self.assertEqual(self.pending_counts(), (0, 0, 0))
        good = publish_pending(self.admissions, self.catalog, revision, [right, left, middle])
        self.assertEqual(tuple(ref.local_id for ref in good.references), (left, middle, right))

    def test_mixed_source(self):
        revision = self.freeze_pending_values([0, (1, 2), 6])
        left = self.issue_pending_range(revision, (1, 2)).to_wire()
        right = self.issue_pending_range(revision, (3, 3)).to_wire()
        foreign = dict(right, source='other-station', segment_id='other-station:segment:0')
        ids = [receive(self.admissions, wire).local_id for wire in (left, foreign)]
        with self.assertRaisesRegex(ValueError, 'MIXED_SOURCE'):
            publish_pending(self.admissions, self.catalog, revision, ids)
        self.assertEqual(self.pending_counts(), (0, 0, 0))

    def test_mixed_version_in_v1_publish(self):
        revision = self.freeze_pending_values([0, (1, 2), 6])
        ids = self.intake_pending(revision, [(1, 2), (3, 3)])
        with self.assertRaisesRegex(ValueError, 'MIXED_VERSION'):
            publish(self.admissions, self.catalog, revision, ids)
        self.assertEqual(self.report_counts(), (0, 0, 0))

    def test_v1_issue_rejects_pending_slots(self):
        revision = self.freeze_pending_values([0, (1, 2), 6])
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_OBSERVATIONS'):
            self.issue_range(revision, (1, 3))
        with self.assertRaisesRegex(ValueError, 'INCOMPLETE_OBSERVATIONS'):
            self.issue_range(revision, (2, 2))
        piece = self.issue_range(revision, (3, 3))
        self.assertEqual(piece.manifest.version, 1)

    def test_pending_limit_at_publish(self):
        wire = {
            'version': 2, 'segment_id': 'crafted:nine', 'source': 'crafted',
            'trial_id': 'crafted-trial', 'revision_id': 'crafted:r1',
            'plan': [1, 9], 'span': [1, 9],
            'payload': {
                'determined': [], 'elided': [],
                'pending': [[slot, ['0', '1']] for slot in range(1, 10)],
                'missing': [],
            },
        }
        local_id = receive(self.admissions, wire).local_id
        with self.assertRaisesRegex(ValueError, 'PENDING_LIMIT'):
            publish_pending(self.admissions, self.catalog, 'crafted:r1', [local_id])
        self.assertEqual(self.pending_counts(), (0, 0, 0))

    def test_pending_commit_failure_and_retry(self):
        revision = self.freeze_pending_values(list(pending_examples.FORK))
        ids = self.intake_pending(revision, [(1, 2), (3, 4)])
        for table in ('pending_reports', 'pending_report_receipts'):
            with self.subTest(table=table):
                with pending_workflow.fail_report_write(self.review, table):
                    with self.assertRaisesRegex(RuntimeError, 'REPORT_COMMIT_FAILED'):
                        publish_pending(self.admissions, self.catalog, revision, ids)
                self.assertEqual(self.pending_counts(), (0, 0, 0))
                self.assertFalse(self.review.in_transaction)
        report = publish_pending(self.admissions, self.catalog, revision, ids)
        self.assertEqual(self.pending_counts(), (1, 2, 1))
        self.assertEqual(read_pending(self.catalog, report.report_id), report)

    def test_pending_readback_after_correction_and_reopen(self):
        revision = self.freeze_pending_values(list(pending_examples.FORK))
        ids = self.intake_pending(revision, [(1, 2), (3, 4)])
        report = publish_pending(
            self.admissions, self.catalog, revision, ids,
            query=(pending_examples.REMAINDER, pending_examples.RANGE_FOUR),
        )
        corrected = self.freeze_pending_values([0, 7, (1, 2, 5), 6])
        self.assertNotEqual(revision, corrected)
        self.source.close()
        self.review.close()
        self.open_review()
        with self.assertRaisesRegex(LookupError, 'REPORT_NOT_FOUND'):
            read_pending(self.catalog, 'pending-report-999')
        for _ in range(2):
            recovered = read_pending(self.catalog, report.report_id)
            self.assertEqual(recovered, report)
            self.assertEqual(recovered.witness, ((3, Fraction(1)),))
            self.assertEqual(recovered.receipt, report.receipt)
            self.assertEqual(recovered.revision_id, revision)

    def test_issue_pending_after_correction(self):
        revision = self.freeze_pending_values([0, (1, 2), 6])
        corrected = self.freeze_pending_values([0, (1, 3), 6])
        old_piece = self.issue_pending_range(revision, (1, 3))
        new_piece = self.issue_pending_range(corrected, (1, 3))
        self.assertNotEqual(old_piece.manifest.segment_id, new_piece.manifest.segment_id)
        self.assertEqual(self.issue_pending_range(revision, (1, 3)), old_piece)
        self.assertEqual(self.register.get(old_piece.manifest.segment_id), old_piece)

    def test_pending_reinitialize(self):
        revision = self.freeze_pending_values([0, (1, 2), 6])
        segment = self.issue_pending_range(revision, (1, 3))
        self.source.close()
        reopened = self.connect(self.source_path)
        revisions = RevisionStore(reopened, 'bench')
        register = IssueRegister(reopened, 'bench')
        for _ in range(2):
            revisions.initialize()
            register.initialize()
        self.assertEqual(revisions.get_pending(revision).observations, (
            Observation(1, Fraction(0)),
            Observation(2, (Fraction(1), Fraction(2))),
            Observation(3, Fraction(6)),
        ))
        self.assertEqual(register.get(segment.manifest.segment_id), segment)

    def test_unknown_pending_ids(self):
        with self.assertRaisesRegex(LookupError, 'REVISION_NOT_FOUND'):
            self.issue_pending_range('unknown-revision', (1, 2))
        with self.assertRaisesRegex(LookupError, 'REPORT_NOT_FOUND'):
            read_pending(self.catalog, 'unknown-report')

    def test_determined_matches_v1(self):
        cases = (
            (0, 5, 1, 6),
            (0, 5, 2, 6),
            (0, 5, 5, 6),
            (0, 5, 5, 2, 6, None, 5, 2),
            (0, 1, 2, 3),
        )
        for values in cases:
            partitions = (((1, len(values)),), tuple((slot, slot) for slot in range(1, len(values) + 1)))
            for cuts in partitions:
                with self.subTest(values=values, cuts=cuts):
                    revision = self.freeze_pending_values(list(values))
                    v1_ids = [
                        receive(self.admissions, self.issue_range(revision, span).to_wire()).local_id
                        for span in cuts
                    ]
                    expected = publish(self.admissions, self.catalog, revision, v1_ids).ledger.cycles
                    v2_ids = self.intake_pending(revision, cuts)
                    report = publish_pending(self.admissions, self.catalog, revision, v2_ids)
                    self.assertEqual(report.possible, expected)
                    self.assertEqual(report.certain, expected)

    def test_elision_cut_invariance(self):
        revision = self.freeze_pending_values([0, '1/2', 2, (0, 3), 6])
        ledgers = set()
        for cuts in (((1, 5),), ((1, 2), (3, 5)), ((1, 3), (4, 5)), ((1, 2), (3, 4), (5, 5))):
            with self.subTest(cuts=cuts):
                ids = self.intake_pending(revision, cuts)
                report = publish_pending(self.admissions, self.catalog, revision, ids)
                ledgers.add((report.possible, report.certain))
        self.assertEqual(len(ledgers), 1)
        (possible, certain), = ledgers
        self.assertIn(Cycle(3, 4, Fraction(2), HALF), possible)
        self.assertEqual(certain, ())

    def test_provided_scripts(self):
        pending_examples.main()
        pending_workflow.run()

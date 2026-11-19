from fractions import Fraction

from segments.manifest import IssueRegister
from tests import LabTestCase
from trial.freeze import freeze
from trial.observations import Observation
from trial.plan import TrialPlan
from trial.revisions import RevisionStore


class TrialTests(LabTestCase):
    def test_freeze_and_issue(self):
        revision = self.freeze_values([0, 5, 5, 5, 2, 6], first=10)
        left = self.issue_range(revision, (10, 12))
        self.assertEqual(self.source_counts(), (1, 1))
        self.assertEqual((left.manifest.first, left.manifest.last), (10, 12))
        self.assertEqual((left.manifest.plan_first, left.manifest.plan_last), (10, 15))
        right = self.issue_range(revision, (13, 15))
        self.assertNotEqual(left.manifest.segment_id, right.manifest.segment_id)
        self.assertEqual((left.manifest.revision_id, right.manifest.revision_id), (revision, revision))
        self.assertEqual(self.revisions.get(revision, first=13, last=15).observations, (
            Observation(13, Fraction(5)), Observation(14, Fraction(2)), Observation(15, Fraction(6)),
        ))
        self.assertEqual(self.source_counts(), (1, 2))

    def test_exact_loads(self):
        revision = self.freeze_values(['72057594037927936.0', '72057594037927937.0', '1/10'])
        frozen = self.revisions.get(revision).observations
        self.assertEqual(frozen[0].load, Fraction(72057594037927936))
        self.assertEqual(frozen[1].load - frozen[0].load, Fraction(1))
        self.assertEqual(frozen[2].load, Fraction(1, 10))
        platforms = self.issue_range(revision, (1, 3)).payload.valid[0].platforms
        self.assertEqual(tuple(item.load for item in platforms), (
            Fraction(72057594037927936), Fraction(72057594037927937), Fraction(1, 10),
        ))

    def test_revision_isolation(self):
        old = self.freeze_values([0, 5, 5])
        earlier = self.issue_range(old, (1, 2))
        corrected = self.freeze_values([0, 7, 5])
        self.assertNotEqual(old, corrected)
        old_piece = self.issue_range(old, (1, 3))
        new_piece = self.issue_range(corrected, (1, 3))
        self.assertEqual(old_piece.manifest.revision_id, old)
        self.assertEqual(new_piece.manifest.revision_id, corrected)
        self.assertEqual([point.load for point in old_piece.payload.valid[0].platforms], [0, 5])
        self.assertEqual([point.load for point in new_piece.payload.valid[0].platforms], [0, 7, 5])
        self.assertEqual(self.register.get(earlier.manifest.segment_id), earlier)

    def test_issue_bounds(self):
        revision = self.freeze_values([0, 5, 5])
        with self.assertRaisesRegex(LookupError, 'REVISION_NOT_FOUND'):
            self.issue_range('unregistered', (1, 2))
        for bounds in ((0, 2), (1, 4), (3, 2), (True, 3)):
            with self.subTest(bounds=bounds):
                with self.assertRaisesRegex(ValueError, 'SEGMENT_BOUNDS'):
                    self.issue_range(revision, bounds)
        self.assertEqual(self.source_counts(), (1, 0))

    def test_evidence_origins(self):
        for values, expected_first in (([0, 5, 5], 2), ([0, 0, 5], 3)):
            with self.subTest(values=values):
                revision = self.freeze_values([*values, 5, 2, 6])
                piece = self.issue_range(revision, (1, 3))
                (run,) = piece.payload.valid
                peak = run.platforms[-1]
                self.assertEqual((peak.first, peak.last, peak.load), (expected_first, 3, Fraction(5)))
        self.assertEqual(self.source_counts(), (2, 2))

    def test_reinitialize(self):
        revision_id = self.freeze_values(['-1/2', None, 0])
        original = self.revisions.get(revision_id)
        piece = self.issue_range(revision_id, (1, 3))
        self.source.close()
        reopened = self.connect(self.source_path)
        revisions = RevisionStore(reopened, 'bench')
        register = IssueRegister(reopened, 'bench')
        for _ in range(2):
            revisions.initialize()
            register.initialize()
        self.assertEqual(revisions.get(revision_id), original)
        self.assertEqual(register.get(piece.manifest.segment_id), piece)
        self.assertEqual(reopened.execute('SELECT COUNT(*) FROM issued_segments').fetchone()[0], 1)

    def test_duplicate_source_slot(self):
        saved = self.freeze_values([1, 0])
        fixed = self.issue_range(saved, (1, 2))
        with self.assertRaisesRegex(ValueError, 'DUPLICATE_SLOT'):
            freeze(self.revisions, TrialPlan('test-trial', 1, 2), [Observation(1, 0), Observation(1, 5)])
        self.assertEqual(self.source_counts(), (1, 1))
        self.assertEqual(self.register.get(fixed.manifest.segment_id), fixed)

    def test_invalid_observations(self):
        plan = TrialPlan('controlled', 1, 2)
        cases = (
            ([Observation(1, 0)], 'INCOMPLETE_OBSERVATIONS'),
            ([Observation(1, 0), Observation(3, 1)], 'OBSERVATION_BOUNDS'),
            ([Observation(True, 0), Observation(2, 1)], 'INVALID_OBSERVATION'),
            *(
                ([Observation(1, 0), Observation(2, invalid)], 'INVALID_LOAD')
                for invalid in (' ', 'noise', '1/0', 'NaN', True, 0.1)
            ),
        )
        for observations, message in cases:
            with self.subTest(observations=observations):
                with self.assertRaisesRegex(ValueError, message):
                    freeze(self.revisions, plan, observations)
        with self.assertRaisesRegex(ValueError, 'INVALID_PLAN'):
            freeze(self.revisions, TrialPlan('controlled', 2, 1), [])
        self.assertEqual(self.source_counts(), (0, 0))
        revision = freeze(self.revisions, plan, [Observation(2, None), Observation(1, 0)])
        self.assertEqual(self.revisions.get(revision).observations, (Observation(1, Fraction(0)), Observation(2, None)))

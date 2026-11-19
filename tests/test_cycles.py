from exchange.admission import receive
from reports.publication import publish
from reports.readback import read
from tests import LabTestCase, cycle_rows, fixture


class CycleTests(LabTestCase):
    def test_plateau_across_cuts(self):
        sample = fixture('loads')
        expected = fixture('expected')['plateau']
        revision = self.freeze_values(sample['values'])
        original = [self.issue_range(revision, span).to_wire() for span in sample['cuts']]
        alternate = [self.issue_range(revision, span).to_wire() for span in sample['alternate_cuts']]
        self.source.close()
        ledgers = []
        for partition in (original, alternate):
            local = [receive(self.admissions, wire).local_id for wire in reversed(partition)]
            report = publish(self.admissions, self.catalog, revision, local)
            self.assertEqual(cycle_rows(report), expected, 'CYCLE_SEAM_MISMATCH')
            self.assertEqual(read(self.catalog, report.report_id).ledger, report.ledger)
            ledgers.append(report.ledger)
        self.assertEqual(ledgers[0], ledgers[1])

    def test_distinct_origins(self):
        sample = fixture('loads')
        expected = fixture('expected')
        for values, truth in ((sample['values'], 'plateau'), (sample['later_peak'], 'later_peak')):
            with self.subTest(values=values):
                revision = self.freeze_values(values)
                local = self.intake(revision, [(4, 6), (1, 3)])
                result = publish(self.admissions, self.catalog, revision, local)
                self.assertEqual(cycle_rows(result), expected[truth])

    def test_external_evidence(self):
        self.source.close()
        external = fixture('external')
        expected = fixture('expected')['plateau']
        for key in ('original', 'alternate'):
            with self.subTest(cuts=key):
                items = external[key]
                ids = [receive(self.admissions, wire).local_id for wire in reversed(items)]
                result = publish(self.admissions, self.catalog, external['revision_id'], ids)
                self.assertEqual(cycle_rows(result), expected, 'CYCLE_SEAM_MISMATCH')
                self.assertEqual([reference.segment_id for reference in result.references], [wire['segment_id'] for wire in items])
                self.assertEqual(read(self.catalog, result.report_id), result)

    def test_monotone_seam(self):
        revision = self.freeze_values([0, 1, 2, 3])
        ids = self.intake(revision, [(3, 4), (1, 2)])
        report = publish(self.admissions, self.catalog, revision, ids)
        self.assertEqual(cycle_rows(report), fixture('expected')['monotone'])

    def test_overlapping_segments(self):
        sample = fixture('loads')
        revision = self.freeze_values(sample['values'])
        ids = self.intake(revision, [(3, 6), (1, 4), (2, 3)])
        report = publish(self.admissions, self.catalog, revision, [*ids, ids[1]])
        self.assertEqual(cycle_rows(report), fixture('expected')['plateau'])
        self.assertEqual([(item.first, item.last) for item in report.references], [(1, 4), (2, 3), (3, 6)])

    def test_equal_ranges(self):
        base = 72057594037927936
        loads = [f'{base + offset}.0' for offset in (0, 5, 2, 5, 1)]
        revision = self.freeze_values(loads)
        ids = self.intake(revision, [(1, 5)])
        report = publish(self.admissions, self.catalog, revision, ids)
        self.assertEqual(cycle_rows(report), fixture('expected')['equal_ranges'])

    def test_missing_sample_separates_cycles(self):
        sample = fixture('loads')
        revision = self.freeze_values(sample['missing_values'])
        ids = self.intake(revision, [(5, 7), (1, 4)])
        report = publish(self.admissions, self.catalog, revision, ids)
        self.assertEqual(cycle_rows(report), fixture('expected')['missing'])
        self.assertEqual([ref.first for ref in report.references], [1, 5])

    def test_empty_runs(self):
        cases = (
            ([None, -2, None, None, 0, None], [(1, 3), (4, 6)]),
            ([None, None], [(1, 2)]),
            ([0], [(1, 1)]),
            (['1/10', '0.1', '0.10'], [(1, 2), (3, 3)]),
        )
        for values, cuts in cases:
            with self.subTest(values=values):
                revision = self.freeze_values(values)
                report = publish(self.admissions, self.catalog, revision, self.intake(revision, cuts))
                self.assertEqual(report.ledger.cycles, ())
                self.assertEqual(read(self.catalog, report.report_id), report)

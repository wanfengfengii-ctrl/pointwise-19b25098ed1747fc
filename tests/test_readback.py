from reports.publication import publish
from reports.readback import read
from tests import LabTestCase, cycle_rows, fixture


class ReadbackTests(LabTestCase):
    def test_frozen_report_after_revision(self):
        sample = fixture('loads')
        original = self.freeze_values(sample['values'], trial_id=sample['trial_id'])
        report = publish(self.admissions, self.catalog, original, self.intake(original, sample['cuts']))
        expected = fixture('expected')['plateau']
        self.assertEqual(cycle_rows(report), expected)
        revised = self.freeze_values(sample['revised_values'], trial_id=sample['trial_id'])
        self.assertNotEqual(original, revised)
        self.source.close()
        self.review.close()
        self.open_review()
        original_counts = self.report_counts()
        for _ in range(2):
            recovered = read(self.catalog, report.report_id)
            self.assertEqual(recovered, report)
            self.assertEqual(recovered.receipt, report.receipt)
            self.assertEqual(recovered.revision_id, original)
            self.assertEqual(cycle_rows(recovered), expected)
        self.assertEqual(self.report_counts(), original_counts)

    def test_unknown_id(self):
        revision = self.freeze_values([0, 1])
        report = publish(self.admissions, self.catalog, revision, self.intake(revision, [(1, 2)]))
        with self.assertRaisesRegex(LookupError, 'REPORT_NOT_FOUND: unknown-report'):
            read(self.catalog, 'unknown-report')
        self.assertEqual(read(self.catalog, report.report_id), report)
        self.assertEqual(self.report_counts(), (1, 1, 1))

    def test_reinitialize(self):
        revision = self.freeze_values(fixture('loads')['values'])
        report = publish(self.admissions, self.catalog, revision, self.intake(revision, [(1, 3), (4, 6)]))
        self.source.close()
        self.review.close()
        self.open_review()
        for _ in range(2):
            self.catalog.initialize()
            self.admissions.initialize()
        self.assertEqual(read(self.catalog, report.report_id), report)
        self.assertEqual(self.report_counts(), (1, 2, 1))

import sqlite3
from copy import deepcopy

from exchange.admission import receive
from reports.publication import publish
from reports.readback import read
from tests import LabTestCase, cycle_rows, fixture


class ReportTests(LabTestCase):
    def test_missing_or_mixed_segments(self):
        trial = self.freeze_values([0, 5, 5, 5, 2, 6])
        corrected = self.freeze_values([0, 7, 5, 5, 2, 6])
        left, right = self.intake(trial, [(1, 3), (4, 6)])
        (new_right,) = self.intake(corrected, [(4, 6)])
        for ids, error in (([left], 'COVERAGE_GAP'), ([left, new_right], 'MIXED_REVISION'),
                           ([left, 'unknown-local'], 'UNKNOWN_SELECTION'), ([], 'COVERAGE_GAP')):
            with self.subTest(ids=ids):
                with self.assertRaisesRegex(ValueError, error):
                    publish(self.admissions, self.catalog, trial, ids)
                self.assertEqual(self.report_counts(), (0, 0, 0))
        good = publish(self.admissions, self.catalog, trial, [right, left])
        self.assertEqual(cycle_rows(good), fixture('expected')['plateau'])

    def test_interior_gap(self):
        revision = self.freeze_values(fixture('loads')['values'])
        left, middle, right = self.intake(revision, [(1, 2), (3, 3), (4, 6)])
        self.assertIsNotNone(self.admissions.get_by_local_id(middle))
        with self.assertRaisesRegex(ValueError, 'COVERAGE_GAP: first uncovered slot 3'):
            publish(self.admissions, self.catalog, revision, [left, right])
        self.assertEqual(self.report_counts(), (0, 0, 0))

    def test_complete_selection(self):
        revision = self.freeze_values(fixture('loads')['values'])
        left, middle, right = self.intake(revision, [(1, 2), (3, 3), (4, 6)])
        report = publish(self.admissions, self.catalog, revision, [right, left, middle])
        self.assertEqual(cycle_rows(report), fixture('expected')['plateau'])
        self.assertEqual(tuple(ref.local_id for ref in report.references), (left, middle, right))
        self.assertEqual(self.report_counts(), (1, 3, 1))

    def test_conflicting_selected_evidence(self):
        external = fixture('external')
        left, right = external['original']
        disputed = deepcopy(external['alternate'][1])
        disputed['payload'] = {'valid': [], 'missing': [[3, 4]]}
        ids = [receive(self.admissions, wire).local_id for wire in (left, right, disputed)]
        with self.assertRaisesRegex(ValueError, 'CONFLICTING_EVIDENCE'):
            publish(self.admissions, self.catalog, external['revision_id'], ids)
        self.assertEqual(self.report_counts(), (0, 0, 0))

    def test_selected_references(self):
        revision = self.freeze_values(fixture('loads')['values'])
        left_piece = self.issue_range(revision, (1, 3))
        right_piece = self.issue_range(revision, (4, 6))
        right = receive(self.admissions, right_piece.to_wire()).local_id
        left = receive(self.admissions, left_piece.to_wire()).local_id
        (extra,) = self.intake(revision, [(1, 6)])
        snapshot = publish(self.admissions, self.catalog, revision, [right, left, right])
        actual = [(ref.local_id, ref.segment_id, ref.source, ref.revision_id, ref.first, ref.last) for ref in snapshot.references]
        self.assertEqual(actual, [
            (left, left_piece.manifest.segment_id, 'bench', revision, 1, 3),
            (right, right_piece.manifest.segment_id, 'bench', revision, 4, 6),
        ])
        self.assertNotIn(extra, [ref.local_id for ref in snapshot.references])
        self.assertEqual(cycle_rows(snapshot), fixture('expected')['plateau'])
        self.assertEqual(read(self.catalog, snapshot.report_id), snapshot)

    def test_commit_failure(self):
        previous = self.freeze_values([0, 1])
        old = publish(self.admissions, self.catalog, previous, self.intake(previous, [(1, 2)]))
        revision = self.freeze_values(fixture('loads')['values'])
        ids = self.intake(revision, [(1, 3), (4, 6)])
        before = self.report_counts()
        self.assertEqual(before, (1, 1, 1))
        self.review.executescript('''
            CREATE TABLE test_commit_parent (id INTEGER PRIMARY KEY);
            CREATE TABLE test_commit_child (
                missing_parent INTEGER NOT NULL REFERENCES test_commit_parent(id)
                    DEFERRABLE INITIALLY DEFERRED
            );
            CREATE TRIGGER test_fail_report_commit AFTER INSERT ON report_receipts
            BEGIN
                INSERT INTO test_commit_child VALUES (1);
            END;
        ''')
        with self.assertRaisesRegex(RuntimeError, 'REPORT_COMMIT_FAILED') as failure:
            publish(self.admissions, self.catalog, revision, ids)
        self.assertIsInstance(failure.exception.__cause__, sqlite3.IntegrityError)
        self.assertFalse(self.review.in_transaction)
        self.assertEqual(self.report_counts(), before)
        self.assertEqual(self.review.execute('SELECT COUNT(*) FROM test_commit_child').fetchone()[0], 0)
        self.review.close()
        self.open_review()
        self.assertEqual(self.report_counts(), before)
        self.assertEqual(read(self.catalog, old.report_id), old)
        self.assertTrue(all(self.admissions.get_by_local_id(local_id) for local_id in ids))
        with self.review:
            self.review.execute('DROP TRIGGER test_fail_report_commit')
        retried = publish(self.admissions, self.catalog, revision, ids)
        self.assertEqual(self.report_counts(), (2, 3, 2))
        self.assertEqual(retried.receipt.report_id, retried.report_id)
        self.assertNotEqual(retried.receipt, old.receipt)
        self.assertEqual(cycle_rows(retried), fixture('expected')['plateau'])
        self.assertEqual(read(self.catalog, retried.report_id), retried)

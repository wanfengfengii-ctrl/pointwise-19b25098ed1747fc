from copy import deepcopy

from exchange.admission import receive
from tests import LabTestCase, fixture


class ExchangeTests(LabTestCase):
    def test_duplicate_delivery(self):
        revision = self.freeze_values([0, 5, 5])
        wire = self.issue_range(revision, (1, 3)).to_wire()
        receipt = receive(self.admissions, wire)
        self.assertEqual(receive(self.admissions, wire), receipt)
        equivalent = deepcopy(wire)
        equivalent['payload']['valid'][0]['platforms'][-1][2] = '5.00'
        self.assertEqual(receive(self.admissions, equivalent), receipt)
        self.assertEqual(self.review.execute('SELECT COUNT(*) FROM admissions').fetchone()[0], 1)
        self.assertEqual(self.admissions.get_by_local_id(receipt.local_id).receipt, receipt)

    def test_external_delivery(self):
        self.source.close()
        wire = fixture('external')['original'][0]
        receipt = receive(self.admissions, wire)
        self.assertEqual((receipt.segment_id, receipt.source), ('ridge-left', 'ridge'))
        self.assertEqual(receive(self.admissions, wire), receipt)
        stored = self.admissions.get_by_local_id(receipt.local_id)
        self.assertEqual(stored.envelope.segment.to_wire(), wire)

    def test_reinitialize(self):
        wire = fixture('external')['original'][0]
        receipt = receive(self.admissions, wire)
        self.review.close()
        self.open_review()
        self.admissions.initialize()
        self.assertEqual(receive(self.admissions, wire), receipt)
        self.assertEqual(self.review.execute('SELECT COUNT(*) FROM admissions').fetchone()[0], 1)

    def test_conflicting_delivery(self):
        wire = fixture('external')['original'][0]
        receipt = receive(self.admissions, wire)
        conflict = deepcopy(wire)
        conflict['payload']['valid'][0]['platforms'][-1][2] = '7'
        with self.assertRaisesRegex(ValueError, 'SEGMENT_CONFLICT'):
            receive(self.admissions, conflict)
        with self.assertRaisesRegex(ValueError, 'SEGMENT_CONFLICT'):
            receive(self.admissions, dict(wire, source='another-station'))
        saved = self.admissions.get_by_local_id(receipt.local_id)
        self.assertEqual(saved.envelope.segment.to_wire(), wire)
        self.assertEqual(saved.receipt, receipt)
        self.assertEqual(receive(self.admissions, wire), receipt)
        self.assertEqual(self.review.execute('SELECT COUNT(*) FROM admissions').fetchone()[0], 1)

    def test_invalid_envelope(self):
        wire = fixture('external')['original'][0]
        receipt = receive(self.admissions, wire)
        invalid = deepcopy(wire)
        invalid['segment_id'] = 'ridge-bad'
        invalid['payload']['valid'][0]['platforms'][-1][1] = 4
        with self.assertRaisesRegex(ValueError, 'INVALID_ENVELOPE'):
            receive(self.admissions, invalid)
        with self.assertRaisesRegex(ValueError, 'INVALID_ENVELOPE'):
            receive(self.admissions, dict(wire, version=True))
        self.assertIsNone(self.admissions.find_by_segment_id('ridge-bad'))
        self.assertEqual(self.admissions.get_by_local_id(receipt.local_id).envelope.segment.to_wire(), wire)
        self.assertEqual(receive(self.admissions, wire), receipt)
        self.assertEqual(self.review.execute('SELECT COUNT(*) FROM admissions').fetchone()[0], 1)

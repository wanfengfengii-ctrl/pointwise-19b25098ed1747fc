import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from exchange.envelope import VerifiedEnvelope, verify_envelope
from exchange.receipts import ReceiveReceipt, make_receive_receipt


@dataclass(frozen=True)
class AdmissionRecord:
    envelope: VerifiedEnvelope
    receipt: ReceiveReceipt


class AdmissionStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        with self.connection:
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS admissions (
                    id INTEGER PRIMARY KEY,
                    segment_id TEXT NOT NULL UNIQUE,
                    local_id TEXT NOT NULL UNIQUE,
                    receipt_id TEXT NOT NULL UNIQUE,
                    content TEXT NOT NULL
                )
            ''')

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            yield

    @staticmethod
    def _unpack(row: tuple | None) -> AdmissionRecord | None:
        if row is None:
            return None
        local_id, receipt_id, content = row
        envelope = verify_envelope(json.loads(content))
        manifest = envelope.segment.manifest
        return AdmissionRecord(
            envelope, ReceiveReceipt(receipt_id, local_id, manifest.segment_id, manifest.source)
        )

    def find_by_segment_id(self, segment_id: str) -> AdmissionRecord | None:
        row = self.connection.execute(
            'SELECT local_id, receipt_id, content FROM admissions WHERE segment_id = ?',
            (segment_id,),
        ).fetchone()
        return self._unpack(row)

    def get_by_local_id(self, local_id: str) -> AdmissionRecord | None:
        row = self.connection.execute(
            'SELECT local_id, receipt_id, content FROM admissions WHERE local_id = ?',
            (local_id,),
        ).fetchone()
        return self._unpack(row)

    def insert(self, envelope: VerifiedEnvelope) -> AdmissionRecord:
        if not self.connection.in_transaction:
            raise RuntimeError('admission insert requires an active intake transaction')
        manifest = envelope.segment.manifest
        number = self.connection.execute('SELECT COALESCE(MAX(id), 0) + 1 FROM admissions').fetchone()[0]
        receipt = make_receive_receipt(number, manifest.segment_id, manifest.source)
        self.connection.execute(
            '''INSERT INTO admissions (id, segment_id, local_id, receipt_id, content)
               VALUES (?, ?, ?, ?, ?)''',
            (number, receipt.segment_id, receipt.local_id, receipt.receipt_id, envelope.content),
        )
        return AdmissionRecord(envelope, receipt)

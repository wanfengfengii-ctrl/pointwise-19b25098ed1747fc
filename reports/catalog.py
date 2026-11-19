import json
import sqlite3

from reports.snapshots import ReportDraft, ReportReceipt, ReportSnapshot, decode_snapshot, encode_snapshot


class ReportCatalog:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('PRAGMA foreign_keys = ON')
        with self.connection:
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY,
                    report_id TEXT NOT NULL UNIQUE,
                    trial_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    cycles TEXT NOT NULL
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS report_references (
                    report_id TEXT NOT NULL REFERENCES reports(report_id),
                    position INTEGER NOT NULL,
                    reference TEXT NOT NULL,
                    PRIMARY KEY (report_id, position)
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS report_receipts (
                    report_id TEXT PRIMARY KEY NOT NULL REFERENCES reports(report_id),
                    receipt_id TEXT NOT NULL UNIQUE
                )
            ''')

    def commit_report(self, draft: ReportDraft) -> ReportSnapshot:
        try:
            with self.connection:
                self.connection.execute('BEGIN IMMEDIATE')
                number = self.connection.execute(
                    'SELECT COALESCE(MAX(id), 0) + 1 FROM reports'
                ).fetchone()[0]
                report_id = f'report-{number}'
                receipt = ReportReceipt(f'publication-{number}', report_id)
                snapshot = ReportSnapshot(
                    report_id, draft.trial_id, draft.revision_id, draft.ledger, draft.references, receipt,
                )
                encoded = encode_snapshot(snapshot)
                self.connection.execute(
                    'INSERT INTO reports (id, report_id, trial_id, revision_id, cycles) VALUES (?, ?, ?, ?, ?)',
                    (number, report_id, draft.trial_id, draft.revision_id, json.dumps(encoded['cycles'])),
                )
                self.connection.executemany(
                    'INSERT INTO report_references (report_id, position, reference) VALUES (?, ?, ?)',
                    (
                        (report_id, position, json.dumps(reference))
                        for position, reference in enumerate(encoded['references'])
                    ),
                )
                self.connection.execute(
                    'INSERT INTO report_receipts (report_id, receipt_id) VALUES (?, ?)',
                    (report_id, encoded['receipt']['receipt_id']),
                )
        except sqlite3.Error as error:
            raise RuntimeError('REPORT_COMMIT_FAILED') from error
        return snapshot

    def find_report(self, report_id: str) -> ReportSnapshot | None:
        row = self.connection.execute(
            '''SELECT reports.trial_id, reports.revision_id, reports.cycles, report_receipts.receipt_id
               FROM reports JOIN report_receipts ON report_receipts.report_id = reports.report_id
               WHERE reports.report_id = ?''',
            (report_id,),
        ).fetchone()
        if row is None:
            return None
        trial_id, revision_id, cycles, receipt_id = row
        references = self.connection.execute(
            'SELECT reference FROM report_references WHERE report_id = ? ORDER BY position',
            (report_id,),
        )
        return decode_snapshot({
            'report_id': report_id,
            'trial_id': trial_id,
            'revision_id': revision_id,
            'cycles': json.loads(cycles),
            'references': [json.loads(reference) for (reference,) in references],
            'receipt': {'report_id': report_id, 'receipt_id': receipt_id},
        })

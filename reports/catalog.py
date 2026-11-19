import json
import sqlite3

from reports.pending import PendingDraft, PendingReport, decode_pending_report, encode_pending_report
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
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS pending_reports (
                    id INTEGER PRIMARY KEY,
                    report_id TEXT NOT NULL UNIQUE,
                    trial_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    possible TEXT NOT NULL,
                    certain TEXT NOT NULL,
                    query TEXT,
                    cooccurs INTEGER,
                    witness TEXT
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS pending_report_references (
                    report_id TEXT NOT NULL REFERENCES pending_reports(report_id),
                    position INTEGER NOT NULL,
                    reference TEXT NOT NULL,
                    PRIMARY KEY (report_id, position)
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS pending_report_receipts (
                    report_id TEXT PRIMARY KEY NOT NULL REFERENCES pending_reports(report_id),
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

    def commit_pending_report(self, draft: PendingDraft) -> PendingReport:
        try:
            with self.connection:
                self.connection.execute('BEGIN IMMEDIATE')
                number = self.connection.execute(
                    'SELECT COALESCE(MAX(id), 0) + 1 FROM pending_reports'
                ).fetchone()[0]
                report_id = f'pending-report-{number}'
                receipt = ReportReceipt(f'pending-publication-{number}', report_id)
                report = PendingReport(
                    report_id=report_id,
                    trial_id=draft.trial_id,
                    revision_id=draft.revision_id,
                    references=draft.references,
                    query=draft.query,
                    possible=draft.possible,
                    certain=draft.certain,
                    cooccurs=draft.cooccurs,
                    witness=draft.witness,
                    receipt=receipt,
                )
                encoded = encode_pending_report(report)
                self.connection.execute(
                    '''INSERT INTO pending_reports
                       (id, report_id, trial_id, revision_id, possible, certain, query, cooccurs, witness)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (
                        number, report_id, draft.trial_id, draft.revision_id,
                        json.dumps(encoded['possible']), json.dumps(encoded['certain']),
                        None if encoded['query'] is None else json.dumps(encoded['query']),
                        None if report.cooccurs is None else int(report.cooccurs),
                        None if encoded['witness'] is None else json.dumps(encoded['witness']),
                    ),
                )
                self.connection.executemany(
                    'INSERT INTO pending_report_references (report_id, position, reference) VALUES (?, ?, ?)',
                    (
                        (report_id, position, json.dumps(reference))
                        for position, reference in enumerate(encoded['references'])
                    ),
                )
                self.connection.execute(
                    'INSERT INTO pending_report_receipts (report_id, receipt_id) VALUES (?, ?)',
                    (report_id, encoded['receipt']['receipt_id']),
                )
        except sqlite3.Error as error:
            raise RuntimeError('REPORT_COMMIT_FAILED') from error
        return report

    def find_pending_report(self, report_id: str) -> PendingReport | None:
        row = self.connection.execute(
            '''SELECT pending_reports.trial_id, pending_reports.revision_id, pending_reports.possible,
                      pending_reports.certain, pending_reports.query, pending_reports.cooccurs,
                      pending_reports.witness, pending_report_receipts.receipt_id
               FROM pending_reports
               JOIN pending_report_receipts ON pending_report_receipts.report_id = pending_reports.report_id
               WHERE pending_reports.report_id = ?''',
            (report_id,),
        ).fetchone()
        if row is None:
            return None
        trial_id, revision_id, possible, certain, query, cooccurs, witness, receipt_id = row
        references = self.connection.execute(
            'SELECT reference FROM pending_report_references WHERE report_id = ? ORDER BY position',
            (report_id,),
        )
        return decode_pending_report({
            'report_id': report_id,
            'trial_id': trial_id,
            'revision_id': revision_id,
            'references': [json.loads(reference) for (reference,) in references],
            'query': None if query is None else json.loads(query),
            'possible': json.loads(possible),
            'certain': json.loads(certain),
            'cooccurs': None if cooccurs is None else bool(cooccurs),
            'witness': None if witness is None else json.loads(witness),
            'receipt': {'report_id': report_id, 'receipt_id': receipt_id},
        })

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

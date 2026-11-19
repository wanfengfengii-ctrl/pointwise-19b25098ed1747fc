"""Call the published pending-review interface once the new entry points are available."""
import sqlite3
from contextlib import closing, contextmanager
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from exchange.admission import receive
from exchange.store import AdmissionStore
from pending_examples import (
    FORK, FORK_CERTAIN, FORK_CUTS, FORK_POSSIBLE, RANGE_FOUR, RANGE_THREE,
    REMAINDER, observations,
)
from reports.catalog import ReportCatalog
from segments.manifest import IssueRegister
from segments.ranges import SegmentRange
from trial.plan import TrialPlan
from trial.revisions import RevisionStore


@contextmanager
def fail_report_write(connection, table):
    name = '"' + table.replace('"', '""') + '"'
    connection.execute(f'''
        CREATE TEMP TRIGGER pending_example_fail AFTER INSERT ON {name}
        BEGIN SELECT RAISE(ABORT, 'fixture report write'); END
    ''')
    try:
        yield
    finally:
        connection.execute('DROP TRIGGER temp.pending_example_fail')


def report_values(report):
    return (
        report.report_id, report.trial_id, report.revision_id, report.references,
        report.query, report.possible, report.certain, report.cooccurs,
        report.witness, report.receipt,
    )


def run():
    from reports.publication import publish_pending
    from reports.readback import read_pending
    from segments.issue import issue_pending
    from trial.freeze import freeze_pending

    station = 'pending-example'
    plan = TrialPlan('CH-pending', 1, len(FORK))
    queries = (
        ((RANGE_THREE, RANGE_FOUR), False, None),
        ((REMAINDER, RANGE_FOUR), True, ((3, Fraction(1)),)),
    )
    issued_reports = []
    with TemporaryDirectory() as directory:
        source_path = Path(directory) / 'source.sqlite'
        review_path = Path(directory) / 'review.sqlite'
        with closing(sqlite3.connect(source_path)) as source:
            revisions = RevisionStore(source, station)
            register = IssueRegister(source, station)
            revisions.initialize()
            register.initialize()
            revision = freeze_pending(revisions, plan, observations(FORK))
            partitions = [
                [issue_pending(revisions, register, revision, SegmentRange(*span)).to_wire() for span in cuts]
                for cuts in FORK_CUTS
            ]

        with closing(sqlite3.connect(review_path)) as review:
            admissions = AdmissionStore(review)
            catalog = ReportCatalog(review)
            admissions.initialize()
            catalog.initialize()
            for cuts, wires in zip(FORK_CUTS, partitions):
                receipts = [receive(admissions, wire) for wire in reversed(wires)]
                assert receive(admissions, wires[-1]) == receipts[0]
                ids = [receipt.local_id for receipt in receipts]
                for query, cooccurs, witness in queries:
                    report = publish_pending(admissions, catalog, revision, ids + ids[:1], query=query)
                    assert (report.trial_id, report.revision_id) == (plan.trial_id, revision)
                    assert (report.query, report.cooccurs, report.witness) == (query, cooccurs, witness)
                    assert (report.possible, report.certain) == (FORK_POSSIBLE, FORK_CERTAIN)
                    assert tuple((ref.first, ref.last) for ref in report.references) == cuts
                    assert tuple(ref.local_id for ref in report.references) == tuple(reversed(ids))
                    assert report.receipt.report_id == report.report_id
                    issued_reports.append((report.report_id, report_values(report)))

        with closing(sqlite3.connect(source_path)) as source:
            revisions = RevisionStore(source, station)
            revisions.initialize()
            corrected = freeze_pending(revisions, plan, observations((0, 7, (1, 2, 5), 6)))
            assert corrected != revision

        with closing(sqlite3.connect(review_path)) as review:
            catalog = ReportCatalog(review)
            catalog.initialize()
            for report_id, expected in issued_reports:
                saved = read_pending(catalog, report_id)
                assert report_values(saved) == expected
                print(f'{saved.report_id} {saved.receipt.receipt_id} same reading={saved.cooccurs} witness={saved.witness}')
                print(f'  possible={saved.possible} certain={saved.certain}')


if __name__ == '__main__':
    run()

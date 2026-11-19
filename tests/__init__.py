import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from exchange.admission import receive
from exchange.store import AdmissionStore
from reports.catalog import ReportCatalog
from segments.issue import issue
from segments.manifest import IssueRegister
from segments.ranges import SegmentRange
from trial.freeze import freeze
from trial.observations import Observation
from trial.plan import TrialPlan
from trial.revisions import RevisionStore


SAMPLES = Path(__file__).resolve().parents[1] / 'samples'


def fixture(name):
    return json.loads((SAMPLES / f'{name}.json').read_text(encoding='utf-8'))


def cycle_rows(snapshot):
    return [
        [cycle.first, cycle.last, str(cycle.range_kn), str(cycle.weight)]
        for cycle in snapshot.ledger.cycles
    ]


class LabTestCase(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.source_path = Path(temporary.name) / 'source.sqlite'
        self.review_path = Path(temporary.name) / 'review.sqlite'
        self.source = self.connect(self.source_path)
        self.revisions = RevisionStore(self.source, 'bench')
        self.register = IssueRegister(self.source, 'bench')
        self.revisions.initialize()
        self.register.initialize()
        self.open_review()

    def connect(self, path):
        connection = sqlite3.connect(path)
        self.addCleanup(connection.close)
        return connection

    def open_review(self):
        self.review = self.connect(self.review_path)
        self.admissions = AdmissionStore(self.review)
        self.catalog = ReportCatalog(self.review)
        self.admissions.initialize()
        self.catalog.initialize()

    def freeze_values(self, loads, *, trial_id='test-trial', first=1):
        plan = TrialPlan(trial_id, first, first + len(loads) - 1)
        observations = (Observation(slot, load) for slot, load in enumerate(loads, first))
        return freeze(self.revisions, plan, observations)

    def issue_range(self, revision_id, bounds):
        return issue(self.revisions, self.register, revision_id, SegmentRange(*bounds))

    def intake(self, revision_id, bounds):
        return [
            receive(self.admissions, self.issue_range(revision_id, span).to_wire()).local_id
            for span in bounds
        ]

    def report_counts(self):
        return tuple(
            self.review.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in ('reports', 'report_references', 'report_receipts')
        )

    def source_counts(self):
        return tuple(
            self.source.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            for table in ('trial_revisions', 'issued_segments')
        )

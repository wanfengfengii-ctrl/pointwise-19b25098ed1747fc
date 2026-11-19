import json
import sqlite3
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

import pending_workflow
from exchange.admission import receive
from exchange.store import AdmissionStore
from reports.catalog import ReportCatalog
from reports.publication import publish
from reports.readback import read
from reports.snapshots import encode_snapshot
from segments.issue import issue
from segments.manifest import IssueRegister
from segments.ranges import SegmentRange
from trial.freeze import freeze
from trial.observations import Observation
from trial.plan import TrialPlan
from trial.revisions import RevisionStore


SAMPLES = Path(__file__).resolve().parent / 'samples'


def _freeze(store, sample, values):
    first = sample['first']
    plan = TrialPlan(sample['trial_id'], first, first + len(values) - 1)
    return freeze(store, plan, (Observation(slot, value) for slot, value in enumerate(values, first)))


def main():
    sample = json.loads((SAMPLES / 'loads.json').read_text(encoding='utf-8'))
    expected = json.loads((SAMPLES / 'expected.json').read_text(encoding='utf-8'))['plateau']
    with TemporaryDirectory() as directory:
        source_path = Path(directory) / 'source.sqlite'
        review_path = Path(directory) / 'review.sqlite'
        with closing(sqlite3.connect(source_path)) as source_db:
            revisions = RevisionStore(source_db, 'demo-bench')
            register = IssueRegister(source_db, 'demo-bench')
            revisions.initialize()
            register.initialize()
            revision = _freeze(revisions, sample, sample['values'])
            fixed = [issue(revisions, register, revision, SegmentRange(*span)) for span in sample['cuts']]

        with closing(sqlite3.connect(review_path)) as review_db:
            admissions = AdmissionStore(review_db)
            catalog = ReportCatalog(review_db)
            admissions.initialize()
            catalog.initialize()
            ids = [receive(admissions, segment.to_wire()).local_id for segment in reversed(fixed)]
            published = publish(admissions, catalog, revision, ids)
            actual = encode_snapshot(published)['cycles']
            if actual != expected:
                raise AssertionError(f'CYCLE_SEAM_MISMATCH: expected {expected}, got {actual}')

        with closing(sqlite3.connect(source_path)) as source_db:
            revisions = RevisionStore(source_db, 'demo-bench')
            revisions.initialize()
            corrected = _freeze(revisions, sample, sample['revised_values'])
            if corrected == revision:
                raise AssertionError('source correction must create a new revision')

        with closing(sqlite3.connect(review_path)) as review_db:
            catalog = ReportCatalog(review_db)
            catalog.initialize()
            recovered = read(catalog, published.report_id)
            downstream_actual = {
                'cycles': encode_snapshot(recovered)['cycles'],
                'revision_id': recovered.revision_id,
                'receipt': asdict(recovered.receipt),
                'spans': [[reference.first, reference.last] for reference in recovered.references],
            }
            downstream_expected = {
                'cycles': expected,
                'revision_id': revision,
                'receipt': asdict(published.receipt),
                'spans': sample['cuts'],
            }
            if recovered != published or downstream_actual != downstream_expected:
                raise AssertionError('archived report and original receipt must survive reopen')

    print(f'{published.report_id}  {revision}  {published.receipt.receipt_id}')
    for cycle in recovered.ledger.cycles:
        print(f'{cycle.first} -> {cycle.last}  {cycle.range_kn} kN  weight {cycle.weight}')
    print('POINTWISE_SCENARIO ' + json.dumps({
        'case_id': 'T5',
        'input': {'trial': sample['trial_id'], 'loads_kn': sample['values'], 'cuts': sample['cuts']},
        'expected': expected,
        'actual': actual,
        'downstream_expected': downstream_expected,
        'downstream_actual': downstream_actual,
        'code_paths': [
            'trial/freeze.py', 'segments/issue.py', 'exchange/admission.py', 'exchange/coverage.py',
            'cycles/reversals.py', 'cycles/counting.py', 'reports/publication.py', 'reports/readback.py',
        ],
        'oracle': 'Hand calculation closes 5 to 2 as a full cycle and leaves 0 to 6 as a half cycle. Reopen must return the same issued receipt and the selected spans.',
    }, sort_keys=True))
    print('PENDING_REVIEW_DEMO alternate cuts, source shutdown and reopen readback')
    pending_workflow.run()


if __name__ == '__main__':
    main()

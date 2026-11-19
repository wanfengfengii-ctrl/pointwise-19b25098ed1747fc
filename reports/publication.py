from collections.abc import Iterable

from cycles.ledger import build_ledger
from exchange.coverage import verify_coverage
from exchange.store import AdmissionStore
from reports.catalog import ReportCatalog
from reports.provenance import build_references
from reports.snapshots import ReportDraft, ReportSnapshot


def publish(
    admissions: AdmissionStore, catalog: ReportCatalog, revision_id: str, local_ids: Iterable[str]
) -> ReportSnapshot:
    selection = verify_coverage(admissions, revision_id, local_ids)
    draft = ReportDraft(
        selection.trial_id, selection.revision_id, build_ledger(selection), build_references(selection),
    )
    return catalog.commit_report(draft)

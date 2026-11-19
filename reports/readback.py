from reports.catalog import ReportCatalog
from reports.snapshots import ReportSnapshot


def read(catalog: ReportCatalog, report_id: str) -> ReportSnapshot:
    snapshot = catalog.find_report(report_id)
    if snapshot is None:
        raise LookupError(f'REPORT_NOT_FOUND: {report_id}')
    return snapshot

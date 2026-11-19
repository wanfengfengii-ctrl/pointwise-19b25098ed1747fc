from collections.abc import Iterable
from fractions import Fraction

from cycles.counting import Cycle
from cycles.ledger import build_ledger
from cycles.pending import iter_readings, reading_cycles, slot_table
from exchange.coverage import verify_coverage, verify_pending_coverage
from exchange.store import AdmissionStore
from reports.catalog import ReportCatalog
from reports.pending import PendingDraft, PendingReport
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


def validate_query(query: object, plan_first: int, plan_last: int) -> tuple | None:
    if query is None:
        return None
    if not isinstance(query, (tuple, list)) or len(query) != 2:
        raise ValueError('INVALID_QUERY: expected an ordered pair of cycles')
    checked = []
    for cycle in query:
        if not isinstance(cycle, Cycle):
            raise ValueError('INVALID_QUERY: expected Cycle entries')
        if (
            type(cycle.first) is not int
            or type(cycle.last) is not int
            or not plan_first <= cycle.first < cycle.last <= plan_last
        ):
            raise ValueError('INVALID_QUERY: cycle bounds must be strictly increasing plan slots')
        if not isinstance(cycle.range_kn, Fraction) or cycle.range_kn <= 0:
            raise ValueError('INVALID_QUERY: cycle range must be a positive Fraction')
        if not isinstance(cycle.weight, Fraction) or cycle.weight not in (Fraction(1, 2), Fraction(1)):
            raise ValueError('INVALID_QUERY: cycle weight must be 1/2 or 1')
        checked.append(cycle)
    return tuple(checked)


def publish_pending(
    admissions: AdmissionStore,
    catalog: ReportCatalog,
    revision_id: str,
    local_ids: Iterable[str],
    *,
    query=None,
) -> PendingReport:
    selection = verify_pending_coverage(admissions, revision_id, local_ids)
    query = validate_query(query, selection.first, selection.last)
    table = slot_table(selection)
    union = set()
    intersection = None
    cooccurs = None
    witness = None
    for reading in iter_readings(table):
        cycles = reading_cycles(table, selection.first, selection.last, reading)
        union |= cycles
        intersection = cycles if intersection is None else intersection & cycles
        if query is not None and witness is None and query[0] in cycles and query[1] in cycles:
            witness = reading
            cooccurs = True
    if query is not None and cooccurs is None:
        cooccurs = False
    order = lambda cycle: (cycle.first, cycle.last, cycle.range_kn, cycle.weight)
    draft = PendingDraft(
        trial_id=selection.trial_id,
        revision_id=selection.revision_id,
        references=build_references(selection),
        query=query,
        possible=tuple(sorted(union, key=order)),
        certain=tuple(sorted(intersection, key=order)),
        cooccurs=cooccurs,
        witness=witness,
    )
    return catalog.commit_pending_report(draft)

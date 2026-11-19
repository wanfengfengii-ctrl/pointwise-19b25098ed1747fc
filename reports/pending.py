from dataclasses import asdict, dataclass
from fractions import Fraction

from cycles.counting import Cycle
from reports.provenance import SegmentReference
from reports.snapshots import ReportReceipt


@dataclass(frozen=True)
class PendingDraft:
    trial_id: str
    revision_id: str
    references: tuple
    query: tuple | None
    possible: tuple
    certain: tuple
    cooccurs: bool | None
    witness: tuple | None


@dataclass(frozen=True)
class PendingReport:
    report_id: str
    trial_id: str
    revision_id: str
    references: tuple
    query: tuple | None
    possible: tuple
    certain: tuple
    cooccurs: bool | None
    witness: tuple | None
    receipt: ReportReceipt


def _encode_cycle(cycle: Cycle) -> list:
    return [cycle.first, cycle.last, str(cycle.range_kn), str(cycle.weight)]


def _decode_cycle(value) -> Cycle:
    first, last, amplitude, weight = value
    return Cycle(first, last, Fraction(amplitude), Fraction(weight))


def encode_pending_report(report: PendingReport) -> dict:
    return {
        'report_id': report.report_id,
        'trial_id': report.trial_id,
        'revision_id': report.revision_id,
        'references': [asdict(reference) for reference in report.references],
        'query': None if report.query is None else [_encode_cycle(cycle) for cycle in report.query],
        'possible': [_encode_cycle(cycle) for cycle in report.possible],
        'certain': [_encode_cycle(cycle) for cycle in report.certain],
        'cooccurs': report.cooccurs,
        'witness': None if report.witness is None else [
            [slot, str(load)] for slot, load in report.witness
        ],
        'receipt': asdict(report.receipt),
    }


def decode_pending_report(document: dict) -> PendingReport:
    query = document['query']
    witness = document['witness']
    return PendingReport(
        document['report_id'],
        document['trial_id'],
        document['revision_id'],
        tuple(SegmentReference(**reference) for reference in document['references']),
        None if query is None else tuple(_decode_cycle(cycle) for cycle in query),
        tuple(_decode_cycle(cycle) for cycle in document['possible']),
        tuple(_decode_cycle(cycle) for cycle in document['certain']),
        document['cooccurs'],
        None if witness is None else tuple((slot, Fraction(load)) for slot, load in witness),
        ReportReceipt(**document['receipt']),
    )

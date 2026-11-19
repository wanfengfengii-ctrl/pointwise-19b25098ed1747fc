from dataclasses import asdict, dataclass
from fractions import Fraction

from cycles.counting import Cycle
from cycles.ledger import CycleLedger
from reports.provenance import SegmentReference


@dataclass(frozen=True)
class ReportDraft:
    trial_id: str
    revision_id: str
    ledger: CycleLedger
    references: tuple[SegmentReference, ...]


@dataclass(frozen=True)
class ReportReceipt:
    receipt_id: str
    report_id: str


@dataclass(frozen=True)
class ReportSnapshot:
    report_id: str
    trial_id: str
    revision_id: str
    ledger: CycleLedger
    references: tuple[SegmentReference, ...]
    receipt: ReportReceipt


def encode_snapshot(snapshot: ReportSnapshot) -> dict:
    return {
        'report_id': snapshot.report_id,
        'trial_id': snapshot.trial_id,
        'revision_id': snapshot.revision_id,
        'cycles': [
            [cycle.first, cycle.last, str(cycle.range_kn), str(cycle.weight)]
            for cycle in snapshot.ledger.cycles
        ],
        'references': [asdict(reference) for reference in snapshot.references],
        'receipt': asdict(snapshot.receipt),
    }


def decode_snapshot(document: dict) -> ReportSnapshot:
    cycles = tuple(
        Cycle(first, last, Fraction(amplitude), Fraction(weight))
        for first, last, amplitude, weight in document['cycles']
    )
    references = tuple(SegmentReference(**reference) for reference in document['references'])
    return ReportSnapshot(
        document['report_id'], document['trial_id'], document['revision_id'],
        CycleLedger(cycles), references, ReportReceipt(**document['receipt']),
    )

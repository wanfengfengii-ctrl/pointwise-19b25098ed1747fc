from collections.abc import Iterable
from dataclasses import dataclass

from exchange.store import AdmissionRecord, AdmissionStore


@dataclass(frozen=True)
class CoveredSelection:
    trial_id: str
    revision_id: str
    first: int
    last: int
    records: tuple[AdmissionRecord, ...]


def _position(record: AdmissionRecord) -> tuple[int, int, str]:
    manifest = record.envelope.segment.manifest
    return manifest.first, manifest.last, record.receipt.local_id


def verify_coverage(
    store: AdmissionStore, revision_id: str, local_ids: Iterable[str]
) -> CoveredSelection:
    if isinstance(local_ids, str):
        raise ValueError('UNKNOWN_SELECTION: expected a collection of local identifiers')
    identifiers = tuple(local_ids)
    if any(not isinstance(identifier, str) or not identifier.strip() for identifier in identifiers):
        raise ValueError('UNKNOWN_SELECTION: invalid local identifier')
    records = []
    for local_id in sorted(set(identifiers)):
        record = store.get_by_local_id(local_id)
        if record is None:
            raise ValueError(f'UNKNOWN_SELECTION: {local_id}')
        records.append(record)
    if not records:
        raise ValueError('COVERAGE_GAP: no selected segments')
    records.sort(key=_position)
    declared = records[0].envelope.segment.manifest
    expected = (declared.trial_id, revision_id, declared.plan_first, declared.plan_last)
    for record in records:
        manifest = record.envelope.segment.manifest
        if (manifest.trial_id, manifest.revision_id, manifest.plan_first, manifest.plan_last) != expected:
            raise ValueError(f'MIXED_REVISION: {record.receipt.local_id}')
    cursor = declared.plan_first
    for record in records:
        manifest = record.envelope.segment.manifest
        if manifest.first > cursor:
            raise ValueError(f'COVERAGE_GAP: first uncovered slot {cursor}')
        cursor = max(cursor, manifest.last + 1)
    if cursor != declared.plan_last + 1:
        raise ValueError(f'COVERAGE_GAP: first uncovered slot {cursor}')
    return CoveredSelection(*expected, tuple(records))

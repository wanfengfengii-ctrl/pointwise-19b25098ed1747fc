from dataclasses import dataclass

from exchange.coverage import CoveredSelection
from segments.payload import PlateauEvidence


@dataclass(frozen=True)
class ContinuousRun:
    first: int
    last: int
    platforms: tuple[PlateauEvidence, ...]


def _union(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged = []
    for first, last in sorted(intervals):
        if merged and first <= merged[-1][1] + 1:
            previous_first, previous_last = merged[-1]
            merged[-1] = (previous_first, max(previous_last, last))
        else:
            merged.append((first, last))
    return merged


def assemble_runs(selection: CoveredSelection) -> tuple[ContinuousRun, ...]:
    valid = []
    missing = []
    candidates = []
    for record in selection.records:
        payload = record.envelope.segment.payload
        missing.extend((span.first, span.last) for span in payload.missing)
        for run in payload.valid:
            valid.append((run.first, run.last))
            candidates.extend(run.platforms)

    valid_intervals = _union(valid)
    cursor = selection.first
    for first, last in sorted(valid_intervals + _union(missing)):
        if first != cursor:
            raise ValueError(f'CONFLICTING_EVIDENCE: disputed valid or missing slot near {first}')
        cursor = last + 1
    if cursor != selection.last + 1:
        raise ValueError('CONFLICTING_EVIDENCE: incomplete evidence span')

    candidates.sort(key=lambda platform: (platform.first, platform.last))
    assembled = []
    index = 0
    for first, last in valid_intervals:
        start = index
        while index < len(candidates) and candidates[index].first <= last:
            index += 1
        assembled.append(ContinuousRun(first, last, tuple(candidates[start:index])))
    return tuple(assembled)

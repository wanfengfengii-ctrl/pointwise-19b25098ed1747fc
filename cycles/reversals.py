from dataclasses import dataclass
from fractions import Fraction

from cycles.continuity import ContinuousRun
from segments.payload import PlateauEvidence, turning_platforms


@dataclass(frozen=True)
class Reversal:
    slot: int
    load: Fraction


def _merge_platforms(platforms: tuple[PlateauEvidence, ...]) -> tuple[PlateauEvidence, ...]:
    merged = []
    for point in platforms:
        if not merged:
            merged.append(point)
            continue
        previous = merged[-1]
        if point.load == previous.load:
            if point.first > previous.last + 1:
                raise ValueError('CONFLICTING_EVIDENCE: separated equal platforms lack intervening evidence')
            merged[-1] = PlateauEvidence(previous.first, max(previous.last, point.last), previous.load)
        else:
            if point.first <= previous.last:
                raise ValueError(f'CONFLICTING_EVIDENCE: conflicting loads at slot {point.first}')
            merged.append(point)
    return tuple(merged)


def find_reversals(run: ContinuousRun) -> tuple[Reversal, ...]:
    platforms = _merge_platforms(run.platforms)
    return tuple(Reversal(point.first, point.load) for point in turning_platforms(platforms))

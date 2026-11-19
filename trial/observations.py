from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from trial.loads import parse_load_kn
from trial.plan import TrialPlan


@dataclass(frozen=True)
class Observation:
    slot: int
    load: int | str | Fraction | tuple | None


def validate_observations(
    plan: TrialPlan, observations: Iterable[Observation]
) -> tuple[Observation, ...]:
    by_slot = {}
    for observation in observations:
        if not isinstance(observation, Observation) or type(observation.slot) is not int:
            raise ValueError('INVALID_OBSERVATION: an integer original slot is required')
        slot = observation.slot
        if not plan.first <= slot <= plan.last:
            raise ValueError(f'OBSERVATION_BOUNDS: {slot}')
        if slot in by_slot:
            raise ValueError(f'DUPLICATE_SLOT: {slot}')
        load = observation.load
        by_slot[slot] = Observation(slot, None if load is None else parse_load_kn(load))
    if len(by_slot) != plan.last - plan.first + 1:
        raise ValueError('INCOMPLETE_OBSERVATIONS: mark each missing observation explicitly')
    return tuple(by_slot[slot] for slot in sorted(by_slot))


def validate_candidates(load: tuple) -> tuple[Fraction, ...]:
    if not 2 <= len(load) <= 3:
        raise ValueError('INVALID_LOAD: a pending load expects two or three candidates')
    candidates = tuple(parse_load_kn(item) for item in load)
    if len(set(candidates)) != len(candidates):
        raise ValueError('INVALID_LOAD: pending candidates must be distinct rational values')
    return candidates


def validate_pending_observations(
    plan: TrialPlan, observations: Iterable[Observation]
) -> tuple[Observation, ...]:
    """Validate a batch where pending slots hold a tuple of candidate loads."""
    by_slot = {}
    pending = 0
    for observation in observations:
        if not isinstance(observation, Observation) or type(observation.slot) is not int:
            raise ValueError('INVALID_OBSERVATION: an integer original slot is required')
        slot = observation.slot
        if not plan.first <= slot <= plan.last:
            raise ValueError(f'OBSERVATION_BOUNDS: {slot}')
        if slot in by_slot:
            raise ValueError(f'DUPLICATE_SLOT: {slot}')
        load = observation.load
        if load is None:
            normalized = None
        elif type(load) is tuple:
            normalized = validate_candidates(load)
            pending += 1
        else:
            normalized = parse_load_kn(load)
        by_slot[slot] = Observation(slot, normalized)
    if len(by_slot) != plan.last - plan.first + 1:
        raise ValueError('INCOMPLETE_OBSERVATIONS: mark each missing observation explicitly')
    if pending > 8:
        raise ValueError('PENDING_LIMIT: at most eight pending slots per revision')
    return tuple(by_slot[slot] for slot in sorted(by_slot))

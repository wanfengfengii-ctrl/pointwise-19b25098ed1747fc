from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from trial.loads import parse_load_kn
from trial.plan import TrialPlan


@dataclass(frozen=True)
class Observation:
    slot: int
    load: int | str | Fraction | None


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

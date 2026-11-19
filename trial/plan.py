from dataclasses import dataclass


@dataclass(frozen=True)
class TrialPlan:
    trial_id: str
    first: int
    last: int


def validate_plan(plan: TrialPlan) -> TrialPlan:
    if not isinstance(plan, TrialPlan):
        raise ValueError('INVALID_PLAN')
    if not isinstance(plan.trial_id, str) or not plan.trial_id.strip():
        raise ValueError('INVALID_PLAN: trial identifier is required')
    if type(plan.first) is not int or type(plan.last) is not int or plan.first > plan.last:
        raise ValueError('INVALID_PLAN: expected an ordered interval of original slots')
    return plan

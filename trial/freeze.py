from collections.abc import Iterable

from trial.observations import Observation, validate_observations
from trial.plan import TrialPlan, validate_plan
from trial.revisions import RevisionStore


def freeze(store: RevisionStore, plan: TrialPlan, observations: Iterable[Observation]) -> str:
    """Freeze an independently validated, complete trial revision."""
    plan = validate_plan(plan)
    fixed = validate_observations(plan, observations)
    return store.save(plan, fixed)

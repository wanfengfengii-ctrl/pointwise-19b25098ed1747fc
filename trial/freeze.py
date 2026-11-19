from collections.abc import Iterable

from trial.observations import Observation, validate_observations, validate_pending_observations
from trial.plan import TrialPlan, validate_plan
from trial.revisions import RevisionStore


def freeze(store: RevisionStore, plan: TrialPlan, observations: Iterable[Observation]) -> str:
    """Freeze an independently validated, complete trial revision."""
    plan = validate_plan(plan)
    fixed = validate_observations(plan, observations)
    return store.save(plan, fixed)


def freeze_pending(store: RevisionStore, plan: TrialPlan, observations: Iterable[Observation]) -> str:
    """Freeze a revision where selected slots hold pending candidate loads."""
    plan = validate_plan(plan)
    fixed = validate_pending_observations(plan, observations)
    return store.save_pending(plan, fixed)

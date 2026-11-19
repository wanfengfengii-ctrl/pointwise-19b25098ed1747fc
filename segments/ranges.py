from dataclasses import dataclass

from trial.plan import TrialPlan


@dataclass(frozen=True)
class SegmentRange:
    first: int
    last: int


def validate_segment_range(plan: TrialPlan, span: SegmentRange) -> SegmentRange:
    if not isinstance(span, SegmentRange) or type(span.first) is not int or type(span.last) is not int:
        raise ValueError('SEGMENT_BOUNDS: expected original slot bounds')
    if not plan.first <= span.first <= span.last <= plan.last:
        raise ValueError('SEGMENT_BOUNDS: outside the fixed trial plan')
    return span

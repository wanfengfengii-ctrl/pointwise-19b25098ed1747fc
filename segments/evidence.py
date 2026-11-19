from collections.abc import Iterable
from fractions import Fraction
from itertools import groupby

from segments.payload import MissingSpan, PlateauEvidence, SegmentPayload, ValidRunEvidence, turning_platforms
from segments.ranges import SegmentRange
from trial.observations import Observation
from trial.revisions import TrialRevision


def _platforms(observations: Iterable[Observation]) -> tuple[PlateauEvidence, ...]:
    platforms = []
    for load, observations_at_load in groupby(observations, key=lambda item: item.load):
        start = end = next(observations_at_load).slot
        for observation in observations_at_load:
            end = observation.slot
        platforms.append(PlateauEvidence(start, end, Fraction(load)))
    return tuple(platforms)


def build_evidence(revision: TrialRevision, span: SegmentRange) -> SegmentPayload:
    observations = tuple(item for item in revision.observations if span.first <= item.slot <= span.last)
    if len(observations) != span.last - span.first + 1:
        raise ValueError('INCOMPLETE_OBSERVATIONS: segment evidence requires its full source range')
    valid = []
    missing = []
    for absent, group in groupby(observations, key=lambda item: item.load is None):
        run = tuple(group)
        first, last = run[0].slot, run[-1].slot
        if absent:
            missing.append(MissingSpan(first, last))
        else:
            valid.append(ValidRunEvidence(first, last, turning_platforms(_platforms(run))))
    return SegmentPayload(tuple(valid), tuple(missing))

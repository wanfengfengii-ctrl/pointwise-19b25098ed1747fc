from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class PlateauEvidence:
    first: int
    last: int
    load: Fraction


@dataclass(frozen=True)
class ValidRunEvidence:
    first: int
    last: int
    platforms: tuple[PlateauEvidence, ...]


@dataclass(frozen=True)
class MissingSpan:
    first: int
    last: int


@dataclass(frozen=True)
class SegmentPayload:
    valid: tuple[ValidRunEvidence, ...]
    missing: tuple[MissingSpan, ...]


def is_turn(left: Fraction, middle: Fraction, right: Fraction) -> bool:
    return (left < middle > right) or (left > middle < right)


def turning_platforms(platforms: tuple[PlateauEvidence, ...]) -> tuple[PlateauEvidence, ...]:
    """Keep both ends and all strict interior extrema of distinct successive platforms."""
    if len(platforms) < 3:
        return platforms
    interior = tuple(
        middle
        for left, middle, right in zip(platforms, platforms[1:], platforms[2:])
        if is_turn(left.load, middle.load, right.load)
    )
    return (platforms[0], *interior, platforms[-1])


def encode_payload(payload: SegmentPayload) -> dict:
    return {
        'valid': [
            {
                'span': [run.first, run.last],
                'platforms': [[point.first, point.last, str(point.load)] for point in run.platforms],
            }
            for run in payload.valid
        ],
        'missing': [[span.first, span.last] for span in payload.missing],
    }


def _bounds(value: object) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('evidence interval must have two bounds')
    first, last = value
    if type(first) is not int or type(last) is not int or first > last:
        raise ValueError('evidence interval has invalid bounds')
    return first, last


def _decode_platform(value: object) -> PlateauEvidence:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError('platform must have bounds and an exact load')
    first, last = _bounds(value[:2])
    if not isinstance(value[2], str):
        raise ValueError('platform load must be exact numeric text')
    try:
        load = Fraction(value[2])
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError('invalid exact platform load') from error
    return PlateauEvidence(first, last, load)


def _decode_run(value: object) -> ValidRunEvidence:
    if not isinstance(value, dict) or value.keys() != {'span', 'platforms'}:
        raise ValueError('invalid valid-run record')
    first, last = _bounds(value['span'])
    if not isinstance(value['platforms'], list) or not value['platforms']:
        raise ValueError('valid run requires endpoint evidence')
    platforms = tuple(_decode_platform(point) for point in value['platforms'])
    if platforms[0].first != first or platforms[-1].last != last:
        raise ValueError('platforms must preserve both run boundaries')
    for left, right in zip(platforms, platforms[1:]):
        if left.last >= right.first or left.load == right.load:
            raise ValueError('platforms must be ordered, disjoint and distinct')
    if turning_platforms(platforms) != platforms:
        raise ValueError('interior evidence must be strict local extrema')
    return ValidRunEvidence(first, last, platforms)


def decode_payload(value: object, first: int, last: int) -> SegmentPayload:
    if not isinstance(value, dict) or value.keys() != {'valid', 'missing'}:
        raise ValueError('invalid segment evidence record')
    if not isinstance(value['valid'], list) or not isinstance(value['missing'], list):
        raise ValueError('valid and missing evidence must be arrays')
    valid = tuple(_decode_run(run) for run in value['valid'])
    missing = tuple(MissingSpan(*_bounds(span)) for span in value['missing'])
    intervals = sorted((*valid, *missing), key=lambda interval: (interval.first, interval.last))
    cursor = first
    previous_type = None
    for interval in intervals:
        if interval.first != cursor or interval.last > last:
            raise ValueError('evidence does not partition the declared segment')
        if type(interval) is previous_type:
            raise ValueError('adjacent fragments of the same kind must form one interval')
        cursor = interval.last + 1
        previous_type = type(interval)
    if cursor != last + 1:
        raise ValueError('evidence does not cover the declared segment')
    return SegmentPayload(
        tuple(sorted(valid, key=lambda run: run.first)),
        tuple(sorted(missing, key=lambda span: span.first)),
    )

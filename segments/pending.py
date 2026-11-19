"""Pending-review (version 2) segment evidence.

A pending segment fixes, for every original slot in its span, one of four
kinds of evidence: an exact determined load, an elided monotone interior
slot whose exact reading stays at the station, a pending slot with two or
three candidate loads, or a true missing span. The evidence is enough to
rebuild turning points and plateau head slots under any complete reading.
"""
from dataclasses import dataclass
from fractions import Fraction

from segments.payload import MissingSpan


@dataclass(frozen=True)
class PendingPayload:
    determined: tuple  # tuple[tuple[int, Fraction], ...]
    elided: tuple  # tuple[int, ...]
    pending: tuple  # tuple[tuple[int, tuple[Fraction, ...]], ...]
    missing: tuple  # tuple[MissingSpan, ...]


def build_pending_evidence(revision, span) -> PendingPayload:
    observations = tuple(item for item in revision.observations if span.first <= item.slot <= span.last)
    if len(observations) != span.last - span.first + 1:
        raise ValueError('INCOMPLETE_OBSERVATIONS: segment evidence requires its full source range')
    by_slot = {item.slot: item.load for item in observations}

    def scalar(slot: int):
        if slot < span.first or slot > span.last:
            return None
        load = by_slot[slot]
        return None if load is None or isinstance(load, tuple) else load

    determined = []
    elided = []
    pending = []
    missing = []
    gap_start = None
    for slot in range(span.first, span.last + 1):
        load = by_slot[slot]
        if load is None:
            if gap_start is None:
                gap_start = slot
            continue
        if gap_start is not None:
            missing.append(MissingSpan(gap_start, slot - 1))
            gap_start = None
        if isinstance(load, tuple):
            pending.append((slot, load))
            continue
        left, right = scalar(slot - 1), scalar(slot + 1)
        if left is not None and right is not None and (left < load < right or left > load > right):
            # Strictly monotone determined interior slot: its exact reading
            # can never be a turning point or plateau edge, so it stays at
            # the station instead of travelling with the segment.
            elided.append(slot)
        else:
            determined.append((slot, load))
    if gap_start is not None:
        missing.append(MissingSpan(gap_start, span.last))
    return PendingPayload(tuple(determined), tuple(elided), tuple(pending), tuple(missing))


def encode_pending_payload(payload: PendingPayload) -> dict:
    return {
        'determined': [[slot, str(load)] for slot, load in payload.determined],
        'elided': list(payload.elided),
        'pending': [[slot, [str(load) for load in candidates]] for slot, candidates in payload.pending],
        'missing': [[span.first, span.last] for span in payload.missing],
    }


def _slot_number(value: object) -> int:
    if type(value) is not int:
        raise ValueError('pending evidence slot must be an integer')
    return value


def _exact_text(value: object) -> Fraction:
    if not isinstance(value, str):
        raise ValueError('pending evidence load must be exact numeric text')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ValueError('invalid exact pending evidence load') from error


def decode_pending_payload(value: object, first: int, last: int) -> PendingPayload:
    if not isinstance(value, dict) or value.keys() != {'determined', 'elided', 'pending', 'missing'}:
        raise ValueError('invalid pending evidence record')
    raw = (value['determined'], value['elided'], value['pending'], value['missing'])
    if any(not isinstance(section, list) for section in raw):
        raise ValueError('pending evidence sections must be arrays')
    determined = []
    for item in value['determined']:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError('determined evidence must pair a slot with a load')
        determined.append((_slot_number(item[0]), _exact_text(item[1])))
    elided = [_slot_number(item) for item in value['elided']]
    pending = []
    for item in value['pending']:
        if not isinstance(item, list) or len(item) != 2 or not isinstance(item[1], list):
            raise ValueError('pending evidence must pair a slot with candidates')
        candidates = tuple(_exact_text(text) for text in item[1])
        if not 2 <= len(candidates) <= 3:
            raise ValueError('pending evidence expects two or three candidates')
        if len(set(candidates)) != len(candidates):
            raise ValueError('pending candidates must be distinct rational values')
        pending.append((_slot_number(item[0]), candidates))
    missing = []
    for item in value['missing']:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError('missing evidence must be a closed interval')
        low, high = _slot_number(item[0]), _slot_number(item[1])
        if low > high:
            raise ValueError('missing evidence has invalid bounds')
        missing.append(MissingSpan(low, high))

    owners = {}

    def claim(slot: int, kind: str) -> None:
        if not first <= slot <= last:
            raise ValueError('pending evidence is outside the declared segment')
        if slot in owners:
            raise ValueError('pending evidence covers a slot twice')
        owners[slot] = kind

    for slot, _ in determined:
        claim(slot, 'd')
    for slot in elided:
        claim(slot, 'e')
    for slot, _ in pending:
        claim(slot, 'p')
    for span in missing:
        for slot in range(span.first, span.last + 1):
            claim(slot, 'm')
    if len(owners) != last - first + 1:
        raise ValueError('pending evidence does not cover the declared segment')

    ordered_missing = tuple(sorted(missing, key=lambda span: span.first))
    for left, right in zip(ordered_missing, ordered_missing[1:]):
        if right.first <= left.last + 1:
            raise ValueError('adjacent missing fragments must form one interval')

    loads = dict(determined)
    elided_set = set(elided)
    for slot in elided:
        if not first < slot < last:
            raise ValueError('elided evidence must be interior to the segment')
        for neighbor in (slot - 1, slot + 1):
            if owners[neighbor] not in ('d', 'e'):
                raise ValueError('elided evidence requires determined neighbors')
    slot = first
    while slot <= last:
        if slot not in elided_set:
            slot += 1
            continue
        end = slot
        while end + 1 in elided_set:
            end += 1
        if loads[slot - 1] == loads[end + 1]:
            raise ValueError('elided evidence requires distinct monotone bounds')
        slot = end + 1

    return PendingPayload(
        tuple(sorted(determined)),
        tuple(sorted(elided)),
        tuple(sorted(pending)),
        ordered_missing,
    )

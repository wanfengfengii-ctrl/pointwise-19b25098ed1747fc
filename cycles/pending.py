"""Enumerate complete readings of a pending selection and count cycles per reading.

Elided slots are strictly monotone determined interior slots whose exact
readings stayed at the station. They can never be turning points or plateau
edges, so each forms a singleton platform that is dropped before the turning
platforms are taken; dropping a monotone interior platform never changes the
remaining platforms' extrema, so the V1 counting rule applies unchanged.
"""
from itertools import product

from cycles.counting import Cycle, count_cycles
from cycles.reversals import Reversal
from segments.payload import PlateauEvidence, turning_platforms

_MISSING = 'm'
_DETERMINED = 'd'
_ELIDED = 'e'
_PENDING = 'p'


def slot_table(selection) -> dict:
    """Flatten selected pending payloads into per-slot evidence tags."""
    table = {}
    for record in selection.records:
        payload = record.envelope.segment.payload
        for slot, load in payload.determined:
            table[slot] = (_DETERMINED, load)
        for slot in payload.elided:
            table[slot] = (_ELIDED, None)
        for slot, candidates in payload.pending:
            table[slot] = (_PENDING, candidates)
        for span in payload.missing:
            for slot in range(span.first, span.last + 1):
                table[slot] = (_MISSING, None)
    return table


def iter_readings(table: dict):
    """Yield every complete reading as a slot-ascending tuple of (slot, load)."""
    slots = [slot for slot, (kind, _) in sorted(table.items()) if kind == _PENDING]
    candidates = [table[slot][1] for slot in slots]
    for combo in product(*candidates):
        yield tuple(zip(slots, combo))


def _run_cycles(table: dict, first: int, last: int, assignment: dict) -> list:
    rows = []
    slot = first
    while slot <= last:
        if table[slot][0] == _MISSING:
            slot += 1
            continue
        run_end = slot
        while run_end < last and table[run_end + 1][0] != _MISSING:
            run_end += 1
        platforms = []
        cursor = slot
        while cursor <= run_end:
            kind, load = table[cursor]
            if kind == _ELIDED:
                platforms.append(PlateauEvidence(cursor, cursor, None))
                cursor += 1
                continue
            value = load if kind == _DETERMINED else assignment[cursor]
            end = cursor
            while end < run_end:
                next_kind, next_load = table[end + 1]
                if next_kind == _ELIDED:
                    break
                next_value = next_load if next_kind == _DETERMINED else assignment[end + 1]
                if next_value != value:
                    break
                end += 1
            platforms.append(PlateauEvidence(cursor, end, value))
            cursor = end + 1
        kept = tuple(point for point in platforms if point.load is not None)
        reversals = tuple(Reversal(point.first, point.load) for point in turning_platforms(kept))
        rows.extend(count_cycles(reversals))
        slot = run_end + 1
    return rows


def reading_cycles(table: dict, first: int, last: int, reading: tuple) -> frozenset:
    """Count the cycles of one continuous plan under one complete reading."""
    return frozenset(_run_cycles(table, first, last, dict(reading)))

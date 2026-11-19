from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction

from cycles.reversals import Reversal


@dataclass(frozen=True)
class Cycle:
    first: int
    last: int
    range_kn: Fraction
    weight: Fraction


_HALF = Fraction(1, 2)
_FULL = Fraction(1)


def _record(rows: list[Cycle], left: Reversal, right: Reversal, weight: Fraction) -> None:
    amplitude = abs(right.load - left.load)
    if amplitude > 0:
        rows.append(Cycle(left.slot, right.slot, amplitude, weight))


def count_cycles(reversals: Iterable[Reversal]) -> tuple[Cycle, ...]:
    """Apply the three-point rule to one continuous interval, then settle its remainder."""
    stack = []
    rows = []
    for reversal in reversals:
        stack.append(reversal)
        while len(stack) >= 3:
            first, second, newest = stack[-3:]
            if abs(newest.load - second.load) < abs(second.load - first.load):
                break
            if len(stack) == 3:
                _record(rows, first, second, _HALF)
                del stack[0]
            else:
                _record(rows, first, second, _FULL)
                del stack[-3:-1]
    for first, second in zip(stack, stack[1:]):
        _record(rows, first, second, _HALF)
    return tuple(rows)

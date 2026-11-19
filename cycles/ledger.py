from dataclasses import dataclass

from cycles.continuity import assemble_runs
from cycles.counting import Cycle, count_cycles
from cycles.reversals import find_reversals
from exchange.coverage import CoveredSelection


@dataclass(frozen=True)
class CycleLedger:
    cycles: tuple[Cycle, ...]


def build_ledger(selection: CoveredSelection) -> CycleLedger:
    rows = []
    for run in assemble_runs(selection):
        rows.extend(count_cycles(find_reversals(run)))
    rows.sort(key=lambda cycle: (cycle.first, cycle.last))
    return CycleLedger(tuple(rows))

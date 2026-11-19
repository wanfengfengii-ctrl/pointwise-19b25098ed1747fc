import sqlite3
from contextlib import closing
from fractions import Fraction

from cycles.counting import Cycle
from exchange.admission import receive
from exchange.store import AdmissionStore
from reports.catalog import ReportCatalog
from reports.publication import publish
from segments.issue import issue
from segments.manifest import IssueRegister
from segments.ranges import SegmentRange
from trial.freeze import freeze
from trial.observations import Observation
from trial.plan import TrialPlan
from trial.revisions import RevisionStore


FORK = (0, 5, (1, 2, 5), 6)
FORK_CUTS = (((1, 2), (3, 4)), ((1, 3), (4, 4)))
HALF = Fraction(1, 2)
FULL = Fraction(1)
REMAINDER = Cycle(1, 4, Fraction(6), HALF)
RANGE_THREE = Cycle(2, 3, Fraction(3), FULL)
RANGE_FOUR = Cycle(2, 3, Fraction(4), FULL)
FORK_POSSIBLE = (REMAINDER, RANGE_THREE, RANGE_FOUR)
FORK_CERTAIN = (REMAINDER,)
SEAM = (0, 5, (5, 6), 2, 6, None, 5, 2)
SEAM_CUTS = (((1, 2), (3, 5), (6, 8)), ((1, 3), (4, 8)))


def observations(values):
    return tuple(Observation(slot, value) for slot, value in enumerate(values, 1))


def determined(values, cuts):
    with closing(sqlite3.connect(":memory:")) as source:
        revisions = RevisionStore(source, "sample")
        register = IssueRegister(source, "sample")
        revisions.initialize()
        register.initialize()
        revision = freeze(revisions, TrialPlan("sample", 1, len(values)), observations(values))
        wires = [issue(revisions, register, revision, SegmentRange(*cut)).to_wire() for cut in cuts]
    with closing(sqlite3.connect(":memory:")) as review:
        admissions = AdmissionStore(review)
        catalog = ReportCatalog(review)
        admissions.initialize()
        catalog.initialize()
        ids = [receive(admissions, wire).local_id for wire in reversed(wires)]
        ledger = publish(admissions, catalog, revision, ids).ledger.cycles
    return tuple(wire["payload"] for wire in wires), ledger


def main():
    for cut in FORK_CUTS:
        for value, expected in ((1, (REMAINDER, RANGE_FOUR)), (2, (REMAINDER, RANGE_THREE)), (5, (REMAINDER,))):
            actual = determined((0, 5, value, 6), cut)[1]
            assert actual == expected, (value, cut, expected, actual)
    for cut in SEAM_CUTS:
        for value, first, amplitude in ((5, 2, 3), (6, 3, 4)):
            expected = (Cycle(1, 5, Fraction(6), HALF), Cycle(first, 4, Fraction(amplitude), FULL), Cycle(7, 8, Fraction(3), HALF))
            actual = determined((0, 5, value, 2, 6, None, 5, 2), cut)[1]
            assert actual == expected, (value, cut, expected, actual)
    span = ((1, 4),)
    assert determined((0, 1, 3, 6), span)[0] == determined((0, 2, 3, 6), span)[0]
    for height in (1, 2):
        expected = (Cycle(1, 2, Fraction(height), HALF), Cycle(2, 3, Fraction(height), HALF), Cycle(3, 4, Fraction(6), HALF))
        assert determined((0, height, 0, 6), span)[1] == expected
    print("V1 oracle: matched determinate branches, cut changes, true missing slot and compression collision")


if __name__ == "__main__":
    main()

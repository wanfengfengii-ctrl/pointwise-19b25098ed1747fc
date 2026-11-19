import json
import sqlite3
from dataclasses import dataclass
from fractions import Fraction

from trial.observations import Observation
from trial.plan import TrialPlan


@dataclass(frozen=True)
class TrialRevision:
    revision_id: str
    plan: TrialPlan
    observations: tuple[Observation, ...]


class RevisionStore:
    def __init__(self, connection: sqlite3.Connection, station: str):
        if not isinstance(station, str) or not station.strip():
            raise ValueError('INVALID_STATION')
        self.connection = connection
        self.station = station

    def initialize(self) -> None:
        self.connection.execute('PRAGMA foreign_keys = ON')
        with self.connection:
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS trial_revisions (
                    id INTEGER PRIMARY KEY,
                    revision_id TEXT NOT NULL UNIQUE,
                    trial_id TEXT NOT NULL,
                    first_slot TEXT NOT NULL,
                    last_slot TEXT NOT NULL
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS trial_observations (
                    revision INTEGER NOT NULL REFERENCES trial_revisions(id),
                    offset INTEGER NOT NULL,
                    load_kn TEXT,
                    PRIMARY KEY (revision, offset)
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS trial_pending_loads (
                    revision INTEGER NOT NULL REFERENCES trial_revisions(id),
                    offset INTEGER NOT NULL,
                    candidates TEXT NOT NULL,
                    PRIMARY KEY (revision, offset)
                )
            ''')

    def save(self, plan: TrialPlan, observations: tuple[Observation, ...]) -> str:
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            number = self.connection.execute(
                'SELECT COALESCE(MAX(id), 0) + 1 FROM trial_revisions'
            ).fetchone()[0]
            revision_id = f'{self.station}:r{number}'
            self.connection.execute(
                'INSERT INTO trial_revisions VALUES (?, ?, ?, ?, ?)',
                (number, revision_id, plan.trial_id, str(plan.first), str(plan.last)),
            )
            self.connection.executemany(
                'INSERT INTO trial_observations (revision, offset, load_kn) VALUES (?, ?, ?)',
                (
                    (number, item.slot - plan.first, None if item.load is None else str(item.load))
                    for item in observations
                ),
            )
        return revision_id

    def save_pending(self, plan: TrialPlan, observations: tuple[Observation, ...]) -> str:
        """Persist a revision whose pending slots carry candidate tuples."""
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            number = self.connection.execute(
                'SELECT COALESCE(MAX(id), 0) + 1 FROM trial_revisions'
            ).fetchone()[0]
            revision_id = f'{self.station}:r{number}'
            self.connection.execute(
                'INSERT INTO trial_revisions VALUES (?, ?, ?, ?, ?)',
                (number, revision_id, plan.trial_id, str(plan.first), str(plan.last)),
            )
            self.connection.executemany(
                'INSERT INTO trial_observations (revision, offset, load_kn) VALUES (?, ?, ?)',
                (
                    (number, item.slot - plan.first, None if item.load is None else str(item.load))
                    for item in observations
                    if not isinstance(item.load, tuple)
                ),
            )
            self.connection.executemany(
                'INSERT INTO trial_pending_loads (revision, offset, candidates) VALUES (?, ?, ?)',
                (
                    (number, item.slot - plan.first, json.dumps([str(load) for load in item.load]))
                    for item in observations
                    if isinstance(item.load, tuple)
                ),
            )
        return revision_id

    def _metadata(self, revision_id: str) -> tuple[int, TrialPlan]:
        row = self.connection.execute(
            'SELECT id, trial_id, first_slot, last_slot FROM trial_revisions WHERE revision_id = ?',
            (revision_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f'REVISION_NOT_FOUND: {revision_id}')
        number, trial_id, first, last = row
        return number, TrialPlan(trial_id, int(first), int(last))

    def get_plan(self, revision_id: str) -> TrialPlan:
        return self._metadata(revision_id)[1]

    def get(
        self, revision_id: str, *, first: int | None = None, last: int | None = None
    ) -> TrialRevision:
        number, plan = self._metadata(revision_id)
        first = plan.first if first is None else first
        last = plan.last if last is None else last
        if type(first) is not int or type(last) is not int or not plan.first <= first <= last <= plan.last:
            raise ValueError('SEGMENT_BOUNDS: outside the fixed trial plan')
        rows = self.connection.execute(
            '''SELECT offset, load_kn FROM trial_observations
               WHERE revision = ? AND offset BETWEEN ? AND ? ORDER BY offset''',
            (number, first - plan.first, last - plan.first),
        )
        observations = tuple(
            Observation(plan.first + offset, None if load is None else Fraction(load))
            for offset, load in rows
        )
        return TrialRevision(revision_id, plan, observations)

    def get_pending(
        self, revision_id: str, *, first: int | None = None, last: int | None = None
    ) -> TrialRevision:
        """Read a revision with pending candidate tuples restored per slot."""
        number, plan = self._metadata(revision_id)
        first = plan.first if first is None else first
        last = plan.last if last is None else last
        if type(first) is not int or type(last) is not int or not plan.first <= first <= last <= plan.last:
            raise ValueError('SEGMENT_BOUNDS: outside the fixed trial plan')
        rows = self.connection.execute(
            '''SELECT offset, load_kn FROM trial_observations
               WHERE revision = ? AND offset BETWEEN ? AND ? ORDER BY offset''',
            (number, first - plan.first, last - plan.first),
        )
        by_slot = {}
        for offset, load in rows:
            slot = plan.first + offset
            by_slot[slot] = Observation(slot, None if load is None else Fraction(load))
        pending_rows = self.connection.execute(
            '''SELECT offset, candidates FROM trial_pending_loads
               WHERE revision = ? AND offset BETWEEN ? AND ? ORDER BY offset''',
            (number, first - plan.first, last - plan.first),
        )
        for offset, candidates in pending_rows:
            slot = plan.first + offset
            by_slot[slot] = Observation(slot, tuple(Fraction(item) for item in json.loads(candidates)))
        observations = tuple(by_slot[slot] for slot in sorted(by_slot))
        return TrialRevision(revision_id, plan, observations)

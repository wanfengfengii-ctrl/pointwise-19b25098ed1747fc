import json
import sqlite3
from dataclasses import dataclass

from segments.payload import SegmentPayload, decode_payload, encode_payload


@dataclass(frozen=True)
class SegmentManifest:
    segment_id: str
    source: str
    trial_id: str
    revision_id: str
    plan_first: int
    plan_last: int
    first: int
    last: int
    version: int = 1


@dataclass(frozen=True)
class IssuedSegment:
    manifest: SegmentManifest
    payload: SegmentPayload

    def to_wire(self) -> dict:
        manifest = self.manifest
        return {
            'version': manifest.version,
            'segment_id': manifest.segment_id,
            'source': manifest.source,
            'trial_id': manifest.trial_id,
            'revision_id': manifest.revision_id,
            'plan': [manifest.plan_first, manifest.plan_last],
            'span': [manifest.first, manifest.last],
            'payload': encode_payload(self.payload),
        }


def _restore(wire: dict) -> IssuedSegment:
    manifest = SegmentManifest(
        wire['segment_id'], wire['source'], wire['trial_id'], wire['revision_id'],
        *wire['plan'], *wire['span'], version=wire['version'],
    )
    return IssuedSegment(manifest, decode_payload(wire['payload'], manifest.first, manifest.last))


class IssueRegister:
    def __init__(self, connection: sqlite3.Connection, station: str):
        if not isinstance(station, str) or not station.strip():
            raise ValueError('INVALID_STATION')
        self.connection = connection
        self.station = station

    def initialize(self) -> None:
        with self.connection:
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS issued_segments (
                    segment_id TEXT PRIMARY KEY NOT NULL,
                    content TEXT NOT NULL
                )
            ''')

    def save(self, segment: IssuedSegment) -> IssuedSegment:
        segment_id = segment.manifest.segment_id
        content = json.dumps(segment.to_wire(), sort_keys=True, separators=(',', ':'))
        with self.connection:
            self.connection.execute('BEGIN IMMEDIATE')
            self.connection.execute(
                '''INSERT INTO issued_segments (segment_id, content) VALUES (?, ?)
                   ON CONFLICT(segment_id) DO NOTHING''',
                (segment_id, content),
            )
            stored = self.get(segment_id)
            if stored != segment:
                raise ValueError(f'ISSUE_CONFLICT: {segment_id}')
        return stored

    def get(self, segment_id: str) -> IssuedSegment:
        row = self.connection.execute(
            'SELECT content FROM issued_segments WHERE segment_id = ?', (segment_id,)
        ).fetchone()
        if row is None:
            raise LookupError(f'ISSUED_SEGMENT_NOT_FOUND: {segment_id}')
        return _restore(json.loads(row[0]))

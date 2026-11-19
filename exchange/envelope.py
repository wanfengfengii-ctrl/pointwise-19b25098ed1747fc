import json
from dataclasses import dataclass

from segments.manifest import IssuedSegment, SegmentManifest, decode_versioned_payload


@dataclass(frozen=True)
class VerifiedEnvelope:
    segment: IssuedSegment
    content: str


def canonical_content(segment: IssuedSegment) -> str:
    return json.dumps(segment.to_wire(), sort_keys=True, separators=(',', ':'))


def _interval(value: object) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError('expected a pair of original slot bounds')
    first, last = value
    if type(first) is not int or type(last) is not int or first > last:
        raise ValueError('invalid original slot bounds')
    return first, last


def verify_envelope(wire: object) -> VerifiedEnvelope:
    identifiers = ('segment_id', 'source', 'trial_id', 'revision_id')
    if not isinstance(wire, dict) or wire.keys() != {*identifiers, 'version', 'plan', 'span', 'payload'}:
        raise ValueError('INVALID_ENVELOPE: unexpected fields')
    if type(wire['version']) is not int or wire['version'] not in (1, 2):
        raise ValueError('INVALID_ENVELOPE: unsupported version')
    version = wire['version']
    for field in identifiers:
        if not isinstance(wire[field], str) or not wire[field].strip():
            raise ValueError(f'INVALID_ENVELOPE: {field} is required')
    try:
        plan_first, plan_last = _interval(wire['plan'])
        first, last = _interval(wire['span'])
        if not plan_first <= first <= last <= plan_last:
            raise ValueError('segment is outside declared plan')
        payload = decode_versioned_payload(version, wire['payload'], first, last)
    except ValueError as error:
        raise ValueError(f'INVALID_ENVELOPE: {error}') from error
    manifest = SegmentManifest(
        *(wire[field] for field in identifiers), plan_first, plan_last, first, last, version=version,
    )
    segment = IssuedSegment(manifest, payload)
    return VerifiedEnvelope(segment, canonical_content(segment))

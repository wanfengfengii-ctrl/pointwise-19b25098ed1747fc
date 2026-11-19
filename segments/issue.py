import hashlib
import json

from segments.evidence import build_evidence
from segments.manifest import IssueRegister, IssuedSegment, SegmentManifest
from segments.pending import build_pending_evidence
from segments.ranges import SegmentRange, validate_segment_range
from trial.revisions import RevisionStore


def issue(
    revisions: RevisionStore, register: IssueRegister, revision_id: str, span: SegmentRange
) -> IssuedSegment:
    plan = revisions.get_plan(revision_id)
    bounds = validate_segment_range(plan, span)
    source = revisions.get(revision_id, first=bounds.first, last=bounds.last)
    identity = json.dumps([register.station, revision_id, bounds.first, bounds.last]).encode('ascii')
    segment_id = f'{register.station}:segment:{hashlib.sha256(identity).hexdigest()}'
    manifest = SegmentManifest(
        segment_id, register.station, plan.trial_id, revision_id,
        plan.first, plan.last, bounds.first, bounds.last,
    )
    return register.save(IssuedSegment(manifest, build_evidence(source, bounds)))


def issue_pending(
    revisions: RevisionStore, register: IssueRegister, revision_id: str, span: SegmentRange
) -> IssuedSegment:
    """Issue a version 2 segment carrying pending-review evidence."""
    plan = revisions.get_plan(revision_id)
    bounds = validate_segment_range(plan, span)
    source = revisions.get_pending(revision_id, first=bounds.first, last=bounds.last)
    identity = json.dumps([register.station, revision_id, bounds.first, bounds.last, 2]).encode('ascii')
    segment_id = f'{register.station}:segment:{hashlib.sha256(identity).hexdigest()}'
    manifest = SegmentManifest(
        segment_id, register.station, plan.trial_id, revision_id,
        plan.first, plan.last, bounds.first, bounds.last, version=2,
    )
    return register.save(IssuedSegment(manifest, build_pending_evidence(source, bounds)))

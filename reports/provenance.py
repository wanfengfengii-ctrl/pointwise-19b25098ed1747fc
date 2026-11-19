from dataclasses import dataclass

from exchange.coverage import CoveredSelection


@dataclass(frozen=True)
class SegmentReference:
    local_id: str
    segment_id: str
    source: str
    revision_id: str
    first: int
    last: int


def build_references(selection: CoveredSelection) -> tuple[SegmentReference, ...]:
    references = []
    for record in selection.records:
        manifest = record.envelope.segment.manifest
        references.append(SegmentReference(
            record.receipt.local_id, manifest.segment_id, manifest.source,
            manifest.revision_id, manifest.first, manifest.last,
        ))
    return tuple(references)

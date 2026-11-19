from exchange.envelope import verify_envelope
from exchange.receipts import ReceiveReceipt
from exchange.store import AdmissionStore


def receive(store: AdmissionStore, wire: object) -> ReceiveReceipt:
    envelope = verify_envelope(wire)
    segment_id = envelope.segment.manifest.segment_id
    with store.transaction():
        existing = store.find_by_segment_id(segment_id)
        if existing is None:
            record = store.insert(envelope)
        else:
            if existing.envelope.content != envelope.content:
                raise ValueError(f'SEGMENT_CONFLICT: {segment_id}')
            record = existing
    return record.receipt

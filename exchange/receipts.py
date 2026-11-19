from dataclasses import dataclass


@dataclass(frozen=True)
class ReceiveReceipt:
    receipt_id: str
    local_id: str
    segment_id: str
    source: str


def make_receive_receipt(number: int, segment_id: str, source: str) -> ReceiveReceipt:
    return ReceiveReceipt(f'intake-{number}', f'local-{number}', segment_id, source)

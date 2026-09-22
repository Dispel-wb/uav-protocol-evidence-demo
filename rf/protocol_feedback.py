"""Small protocol-validity oracle used to rank demodulation candidates."""
from __future__ import annotations

from typing import Any


CRC_EXTRA = {0: 50, 24: 24, 30: 39, 76: 152, 77: 143}


def crc_x25(data: bytes, extra: int) -> int:
    crc = 0xFFFF
    for byte in data + bytes([extra]):
        value = byte ^ (crc & 0xFF)
        value ^= (value << 4) & 0xFF
        crc = ((crc >> 8) ^ (value << 8) ^ (value << 3) ^ (value >> 4)) & 0xFFFF
    return crc


def mavlink_evidence(data: bytes) -> dict[str, Any]:
    frames = []
    offset = 0
    while offset < len(data):
        if data[offset] not in (0xFD, 0xFE):
            offset += 1
            continue
        version2 = data[offset] == 0xFD
        header = 10 if version2 else 6
        if offset + header > len(data):
            break
        payload_length = data[offset + 1]
        signed = version2 and bool(data[offset + 2] & 1)
        total = header + payload_length + 2 + (13 if signed else 0)
        if offset + total > len(data):
            offset += 1
            continue
        packet = data[offset:offset + total]
        message_id = packet[7] | packet[8] << 8 | packet[9] << 16 if version2 else packet[5]
        extra = CRC_EXTRA.get(message_id)
        observed = packet[header + payload_length] | packet[header + payload_length + 1] << 8
        computed = crc_x25(packet[1:header + payload_length], extra) if extra is not None else None
        valid = computed == observed if computed is not None else None
        frames.append({"offset": offset, "version": 2 if version2 else 1, "messageId": message_id, "length": total, "crcValid": valid})
        offset += total
    return {"frames": frames, "validFrames": sum(frame["crcValid"] is True for frame in frames), "invalidFrames": sum(frame["crcValid"] is False for frame in frames)}

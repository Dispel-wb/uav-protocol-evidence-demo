"""Small protocol-validity oracle used to rank demodulation candidates."""
from __future__ import annotations

import struct
from typing import Any

from rf.protocol_state import COMMAND_NAMES, RESULT_NAMES


CRC_EXTRA = {0: 50, 24: 24, 30: 39, 76: 152, 77: 143}


def _state_fields(message_id: int, payload: bytes) -> dict[str, Any] | None:
    if message_id == 0 and len(payload) >= 9:
        return {"armed": bool(payload[6] & 0x80), "baseMode": payload[6]}
    if message_id == 76 and len(payload) >= 33:
        command = int.from_bytes(payload[28:30], "little")
        return {
            "command": command,
            "commandName": COMMAND_NAMES.get(command, f"MAV_CMD_{command}"),
            "param1": struct.unpack_from("<f", payload)[0],
            "param7": struct.unpack_from("<f", payload, 24)[0],
            "targetSystem": payload[30],
            "targetComponent": payload[31],
        }
    if message_id == 77 and len(payload) >= 3:
        command = int.from_bytes(payload[0:2], "little")
        result = payload[2]
        return {
            "command": command,
            "commandName": COMMAND_NAMES.get(command, f"MAV_CMD_{command}"),
            "result": result,
            "resultName": RESULT_NAMES.get(result, f"RESULT_{result}"),
        }
    return None


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
        payload = packet[header:header + payload_length]
        frames.append({
            "offset": offset,
            "version": 2 if version2 else 1,
            "messageId": message_id,
            "sequence": packet[4] if version2 else packet[2],
            "systemId": packet[5] if version2 else packet[3],
            "componentId": packet[6] if version2 else packet[4],
            "length": total,
            "crcValid": valid,
            "fields": _state_fields(message_id, payload),
        })
        offset += total
    return {"frames": frames, "validFrames": sum(frame["crcValid"] is True for frame in frames), "invalidFrames": sum(frame["crcValid"] is False for frame in frames)}


def update_mavlink_continuity(
    evidence: dict[str, Any],
    last_sequences: dict[tuple[int, int], int],
) -> dict[str, Any]:
    """Update per-source MAVLink sequence continuity using CRC-valid frames."""
    observations = []
    for frame in evidence["frames"]:
        if frame["crcValid"] is not True:
            continue
        key = (frame["systemId"], frame["componentId"])
        previous = last_sequences.get(key)
        sequence = frame["sequence"]
        status, missing = "first", 0
        if previous is not None:
            delta = (sequence - previous) % 256
            if delta == 0:
                status = "duplicate"
            elif delta == 1:
                status = "continuous"
            elif delta <= 127:
                status, missing = "gap", delta - 1
            else:
                status = "out-of-order"
        if status != "out-of-order":
            last_sequences[key] = sequence
        observations.append({
            "systemId": key[0],
            "componentId": key[1],
            "sequence": sequence,
            "previousSequence": previous,
            "status": status,
            "missingFrames": missing,
        })
    return {
        "observations": observations,
        "missingFrames": sum(item["missingFrames"] for item in observations),
        "duplicates": sum(item["status"] == "duplicate" for item in observations),
        "outOfOrder": sum(item["status"] == "out-of-order" for item in observations),
    }

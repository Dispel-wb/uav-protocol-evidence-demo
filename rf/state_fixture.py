"""Deterministic MAVLink command trajectory encoded as fixed-size 2-FSK windows."""
from __future__ import annotations

import struct

import numpy as np

from rf.generate_iq_fixture import PREAMBLE, synthesize
from rf.protocol_feedback import CRC_EXTRA, crc_x25


def mavlink2(
    message_id: int,
    payload: bytes,
    sequence: int,
    system_id: int = 1,
    component_id: int = 1,
) -> bytes:
    header = bytes([
        0xFD, len(payload), 0, 0, sequence, system_id, component_id,
        message_id & 0xFF,
        (message_id >> 8) & 0xFF,
        (message_id >> 16) & 0xFF,
    ])
    checksum = crc_x25(header[1:] + payload, CRC_EXTRA[message_id])
    return header + payload + checksum.to_bytes(2, "little")


def command_payload(command: int, param1: float = 0, param7: float = 0) -> bytes:
    return struct.pack(
        "<7fHBBB",
        param1, 0, 0, 0, 0, 0, param7,
        command, 1, 1, 0,
    )


def trajectory_packets() -> list[bytes]:
    heartbeat_disarmed = bytearray(9)
    heartbeat_armed = bytearray(9)
    heartbeat_armed[6] = 0x80
    return [
        mavlink2(0, heartbeat_disarmed, 0),
        mavlink2(76, command_payload(400, param1=1), 0, 255, 190),
        mavlink2(77, struct.pack("<HB", 400, 0), 1),
        mavlink2(0, heartbeat_armed, 2),
        mavlink2(76, command_payload(22, param7=20), 1, 255, 190),
        mavlink2(77, struct.pack("<HB", 22, 0), 3),
    ]


def synthesize_trajectory() -> tuple[np.ndarray, dict]:
    packets = trajectory_packets()
    sample_rate, symbol_rate, samples_per_symbol = 48_000, 1_200, 40
    largest_burst = (len(PREAMBLE) + max(map(len, packets))) * 8 * samples_per_symbol
    # Keep more than 20% of every window as guard noise so the quantile-based
    # burst detector can estimate its floor even for the longest command frame.
    window_samples = 1_600 + largest_burst + 4_800
    windows = []
    for index, packet in enumerate(packets):
        samples, _ = synthesize(
            payload=packet,
            sample_rate=sample_rate,
            symbol_rate=symbol_rate,
            seed=20261000 + index,
            window_samples=window_samples,
        )
        windows.append(samples)
    truth = {
        "schema": "synthetic-state-trajectory-v1",
        "sampleRate": sample_rate,
        "symbolRate": symbol_rate,
        "windowSamples": window_samples,
        "windows": len(windows),
        "expectedFinalState": "takeoff-accepted",
        "packetHex": [packet.hex(" ").upper() for packet in packets],
        "boundary": "Deterministic synthetic 2-FSK trajectory for software regression only.",
    }
    return np.concatenate(windows), truth

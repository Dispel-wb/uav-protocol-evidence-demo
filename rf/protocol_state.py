"""Incremental MAVLink command, acknowledgement and heartbeat state evidence."""
from __future__ import annotations

from collections import defaultdict
from typing import Any


COMMAND_NAMES = {22: "NAV_TAKEOFF", 400: "COMPONENT_ARM_DISARM"}
RESULT_NAMES = {
    0: "ACCEPTED",
    1: "TEMPORARILY_REJECTED",
    2: "DENIED",
    3: "UNSUPPORTED",
    4: "FAILED",
    5: "IN_PROGRESS",
    6: "CANCELLED",
}


class ProtocolStateTracker:
    """Keep conservative state evidence across decoded RF windows."""

    def __init__(self) -> None:
        self.state = "unknown"
        self.pending: dict[int, list[dict[str, Any]]] = defaultdict(list)
        self.seen_at: dict[tuple[int, int, int, int], int] = {}
        self.timeline: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self.violations: list[dict[str, Any]] = []
        self.ignored_duplicates = 0
        self._finalized = False

    def _transition(
        self,
        frame: dict[str, Any],
        window_index: int,
        next_state: str,
        evidence: str,
    ) -> None:
        if next_state == self.state:
            return
        self.timeline.append({
            "windowIndex": window_index,
            "frameOffset": frame["offset"],
            "from": self.state,
            "to": next_state,
            "evidence": evidence,
        })
        self.state = next_state

    def update(self, frames: list[dict[str, Any]], window_index: int) -> dict[str, Any]:
        if self._finalized:
            raise RuntimeError("protocol state tracker is already finalized")
        before = {
            "timeline": len(self.timeline),
            "links": len(self.links),
            "violations": len(self.violations),
        }
        for frame in frames:
            if frame["crcValid"] is not True or not frame.get("fields"):
                continue
            identity = (
                frame["systemId"],
                frame["componentId"],
                frame["sequence"],
                frame["messageId"],
            )
            last_seen = self.seen_at.get(identity)
            if last_seen is not None and window_index - last_seen <= 1:
                self.seen_at[identity] = window_index
                self.ignored_duplicates += 1
                continue
            self.seen_at[identity] = window_index
            fields = frame["fields"]
            message_id = frame["messageId"]
            if message_id == 0 and frame["componentId"] == 1:
                armed = fields["armed"]
                state = "armed" if armed else "disarmed"
                self._transition(frame, window_index, state, f"HEARTBEAT armed={armed}")
            elif message_id == 76:
                self._handle_command(frame, fields, window_index)
            elif message_id == 77:
                self._handle_ack(frame, fields, window_index)
        self.seen_at = {
            identity: seen_window
            for identity, seen_window in self.seen_at.items()
            if window_index - seen_window <= 1
        }
        return {
            "state": self.state,
            "newTimeline": self.timeline[before["timeline"]:],
            "newLinks": self.links[before["links"]:],
            "newViolations": self.violations[before["violations"]:],
            "ignoredDuplicates": self.ignored_duplicates,
        }

    def _handle_command(
        self,
        frame: dict[str, Any],
        fields: dict[str, Any],
        window_index: int,
    ) -> None:
        command = fields["command"]
        request = {
            "windowIndex": window_index,
            "frameOffset": frame["offset"],
            "command": command,
            "commandName": fields["commandName"],
        }
        self.pending[command].append(request)
        if command == 400:
            state = "arming-requested" if fields["param1"] >= 0.5 else "disarming-requested"
            self._transition(frame, window_index, state, f"COMMAND_LONG {fields['commandName']}")
        elif command == 22:
            if self.state != "armed":
                self.violations.append({
                    "windowIndex": window_index,
                    "frameOffset": frame["offset"],
                    "type": "precondition",
                    "detail": f"TAKEOFF appeared while state was {self.state}; no armed evidence.",
                })
            self._transition(frame, window_index, "takeoff-requested", f"COMMAND_LONG {fields['commandName']}")

    def _handle_ack(
        self,
        frame: dict[str, Any],
        fields: dict[str, Any],
        window_index: int,
    ) -> None:
        command = fields["command"]
        request = self.pending[command].pop(0) if self.pending[command] else None
        if request is None:
            self.violations.append({
                "windowIndex": window_index,
                "frameOffset": frame["offset"],
                "type": "orphan-ack",
                "detail": f"{fields['commandName']} acknowledgement has no observed request.",
            })
            return
        self.links.append({
            "command": fields["commandName"],
            "requestWindowIndex": request["windowIndex"],
            "ackWindowIndex": window_index,
            "result": fields["resultName"],
        })
        if fields["result"] == 0 and command == 400:
            self._transition(frame, window_index, "armed", "ARM_DISARM ACK accepted")
        elif fields["result"] == 0 and command == 22:
            self._transition(frame, window_index, "takeoff-accepted", "TAKEOFF ACK accepted")
        elif fields["result"] != 5:
            evidence = f"{fields['commandName']} ACK {fields['resultName']}"
            self._transition(frame, window_index, "command-rejected", evidence)

    def finalize(self) -> dict[str, Any]:
        if not self._finalized:
            for requests in self.pending.values():
                for request in requests:
                    self.violations.append({
                        "windowIndex": request["windowIndex"],
                        "frameOffset": request["frameOffset"],
                        "type": "missing-ack",
                        "detail": f"{request['commandName']} has no acknowledgement before capture end.",
                    })
            self.pending.clear()
            self._finalized = True
        return {
            "schema": "streaming-protocol-state-evidence-v1",
            "finalState": self.state,
            "timeline": self.timeline,
            "links": self.links,
            "violations": self.violations,
            "ignoredDuplicateFrames": self.ignored_duplicates,
            "boundary": "State is inferred only from CRC-valid observed messages; an accepted TAKEOFF command does not prove that the aircraft left the ground.",
        }

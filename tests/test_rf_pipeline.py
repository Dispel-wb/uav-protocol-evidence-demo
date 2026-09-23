import json
from pathlib import Path
import struct
import tempfile
from threading import Event
import unittest

import numpy as np

from rf.generate_iq_fixture import PAYLOAD, generate, synthesize
from rf.generate_psk_fixture import synthesize_bpsk, synthesize_qpsk
from rf.fsk_demod import demodulate, preprocess
from rf.candidate_selector import select
from rf.protocol_feedback import mavlink_evidence, update_mavlink_continuity
from rf.protocol_state import ProtocolStateTracker
from rf.ring_buffer import ComplexRingBuffer
from rf.stream_capture import ArraySource, CaptureConfig, capture, capture_to_sigmf
from rf.streaming_pipeline import run_streaming
from rf.waveform_selector import select_waveform
from rf.full_pipeline import run as run_full_pipeline
from rf.sigmf_io import load
from rf.signal_quality import analyze, remove_dc
from rf.state_fixture import command_payload, mavlink2, synthesize_trajectory


class RFInputTests(unittest.TestCase):
    def test_sigmf_and_quality_pipeline(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "fixture"
            meta_path, data_path = generate(base)
            self.assertTrue(meta_path.exists())
            self.assertTrue(data_path.exists())
            capture = load(meta_path)
            self.assertEqual(capture.datatype, "cf32_le")
            self.assertEqual(capture.sample_rate, 48_000)
            self.assertEqual(capture.center_frequency, 433_920_000)
            self.assertEqual(capture.samples.size, 11_840)
            report = analyze(capture.samples, capture.sample_rate)
            self.assertEqual(report["schema"], "iq-quality-report-v1")
            self.assertEqual(len(report["bursts"]), 1)
            burst = report["bursts"][0]
            self.assertLessEqual(abs(burst["startSample"] - 1_600), 100)
            self.assertLessEqual(abs(burst["endSample"] - 10_240), 100)
            self.assertGreater(report["estimatedSnrDb"], 12)
            self.assertTrue(abs(report["peakOffsetHz"] - 4_200) < 200 or abs(report["peakOffsetHz"] + 1_800) < 200)
            json.dumps(report)
            processed = preprocess(capture.samples, capture.sample_rate, 1_200)
            self.assertLess(abs(processed["carrierOffsetHz"] - 1_200), 150)
            demod = demodulate(capture.samples, capture.sample_rate, 1_200)
            expected = bytes.fromhex("FD 09 00 00 00 01 01 00 00 00 00 00 00 00 02 03 00 04 03 4A D7")
            self.assertEqual(demod["payload"][:len(expected)], expected)
            self.assertLessEqual(demod["preambleBitErrors"], 2)
            evidence = mavlink_evidence(demod["payload"])
            self.assertEqual(evidence["validFrames"], 1)
            selection = select(capture.samples, capture.sample_rate, [800, 1_000, 1_200, 2_400])
            self.assertEqual(selection["chosenSymbolRate"], 1_200)
            self.assertEqual(selection["validProtocolFrames"], 1)
            self.assertEqual(len(selection["candidates"]), 4)
            config = CaptureConfig(center_frequency=433_920_000, sample_rate=48_000, duration_seconds=capture.samples.size / 48_000, chunk_samples=1024, ring_samples=capture.samples.size)
            full = run_full_pipeline(ArraySource(capture.samples, 48_000), config, [800, 1_200, 2_400])
            self.assertTrue(full["complete"])
            self.assertEqual(full["selection"]["chosenSymbolRate"], 1_200)
            self.assertGreater(full["processingMilliseconds"], 0)

    def test_dc_removal(self):
        samples = np.array([1 + 2j, 3 + 4j], dtype=np.complex64)
        cleaned, offset = remove_dc(samples)
        self.assertAlmostEqual(offset.real, 2)
        self.assertAlmostEqual(offset.imag, 3)
        self.assertAlmostEqual(abs(np.mean(cleaned)), 0)

    def test_gfsk_decodes_and_is_distinguished_from_rectangular_fsk(self):
        rectangular, rectangular_truth = synthesize(seed=71)
        gaussian, gaussian_truth = synthesize(gaussian_bt=0.5, seed=72)
        rectangular_result = select(rectangular, rectangular_truth["sampleRate"], [1_200])
        gaussian_result = select(gaussian, gaussian_truth["sampleRate"], [1_200])
        self.assertEqual(rectangular_result["chosenModulation"], "2-FSK")
        self.assertEqual(gaussian_result["chosenModulation"], "GFSK")
        self.assertEqual(bytes.fromhex(gaussian_result["chosenPayloadHex"]), PAYLOAD)
        self.assertEqual(gaussian_result["validProtocolFrames"], 1)
        unified_rectangular = select_waveform(
            rectangular, rectangular_truth["sampleRate"], [1_200], ["fsk", "bpsk"]
        )
        unified_gaussian = select_waveform(
            gaussian, gaussian_truth["sampleRate"], [1_200], ["fsk", "bpsk"]
        )
        self.assertEqual(unified_rectangular["chosenModulation"], "2-FSK")
        self.assertEqual(unified_gaussian["chosenModulation"], "GFSK")

    def test_bpsk_is_selected_over_fsk_and_streams_to_protocol_state(self):
        samples, truth = synthesize_bpsk(carrier_offset=350, carrier_phase=1.1, seed=73)
        selection = select_waveform(
            samples,
            truth["sampleRate"],
            [800, 1_200, 2_400],
            ["fsk", "bpsk"],
        )
        self.assertEqual(selection["chosenModulation"], "BPSK")
        self.assertEqual(selection["chosenSymbolRate"], 1_200)
        self.assertEqual(selection["validProtocolFrames"], 1)
        self.assertEqual(bytes.fromhex(selection["chosenPayloadHex"]), PAYLOAD)

        config = CaptureConfig(
            center_frequency=433_920_000,
            sample_rate=truth["sampleRate"],
            duration_seconds=samples.size / truth["sampleRate"],
            chunk_samples=740,
            ring_samples=samples.size,
        )
        report = run_streaming(
            ArraySource(samples, truth["sampleRate"]),
            config,
            [800, 1_200, 2_400],
            analysis_window_samples=samples.size,
            modulations=["fsk", "bpsk"],
        )
        window = report["analysis"]["windows"][0]
        self.assertEqual(window["chosenModulation"], "BPSK")
        self.assertEqual(window["chosenDemodulator"], "BPSK")
        self.assertEqual(report["analysis"]["protocolState"]["finalState"], "disarmed")

    def test_qpsk_is_selected_across_all_waveform_candidates(self):
        samples, truth = synthesize_qpsk(carrier_offset=-300, carrier_phase=0.8, seed=74)
        selection = select_waveform(
            samples,
            truth["sampleRate"],
            [800, 1_200, 2_400],
            ["fsk", "bpsk", "qpsk"],
        )
        self.assertEqual(selection["chosenModulation"], "QPSK")
        self.assertEqual(selection["chosenSymbolRate"], 1_200)
        self.assertEqual(selection["validProtocolFrames"], 1)
        self.assertEqual(bytes.fromhex(selection["chosenPayloadHex"]), PAYLOAD)

        config = CaptureConfig(
            center_frequency=433_920_000,
            sample_rate=truth["sampleRate"],
            duration_seconds=samples.size / truth["sampleRate"],
            chunk_samples=470,
            ring_samples=samples.size,
        )
        report = run_streaming(
            ArraySource(samples, truth["sampleRate"]),
            config,
            [800, 1_200, 2_400],
            analysis_window_samples=samples.size,
            modulations=["fsk", "bpsk", "qpsk"],
        )
        window = report["analysis"]["windows"][0]
        self.assertEqual(window["chosenModulation"], "QPSK")
        self.assertEqual(window["chosenDemodulator"], "QPSK")
        self.assertEqual(report["analysis"]["protocolState"]["finalState"], "disarmed")

    def test_mavlink_sequence_continuity_handles_wrap_gap_and_reordering(self):
        state = {}

        def observe(sequence):
            evidence = {"frames": [{
                "crcValid": True,
                "systemId": 1,
                "componentId": 1,
                "sequence": sequence,
            }]}
            return update_mavlink_continuity(evidence, state)["observations"][0]

        self.assertEqual(observe(254)["status"], "first")
        self.assertEqual(observe(255)["status"], "continuous")
        wrapped_gap = observe(1)
        self.assertEqual(wrapped_gap["status"], "gap")
        self.assertEqual(wrapped_gap["missingFrames"], 1)
        self.assertEqual(observe(1)["status"], "duplicate")
        self.assertEqual(observe(250)["status"], "out-of-order")
        self.assertEqual(observe(2)["status"], "continuous")

    def test_protocol_state_tracks_command_ack_and_ignores_duplicate_windows(self):
        heartbeat_disarmed = bytearray(9)
        heartbeat_armed = bytearray(9)
        heartbeat_armed[6] = 0x80
        arm = struct.pack("<7fHBBB", 1, 0, 0, 0, 0, 0, 0, 400, 1, 1, 0)
        takeoff = struct.pack("<7fHBBB", 0, 0, 0, 0, 0, 0, 20, 22, 1, 1, 0)
        arm_ack = struct.pack("<HB", 400, 0)
        takeoff_ack = struct.pack("<HB", 22, 0)
        packets = [
            mavlink2(0, heartbeat_disarmed, 0),
            mavlink2(76, arm, 0, 255, 190),
            mavlink2(77, arm_ack, 1),
            mavlink2(0, heartbeat_armed, 2),
            mavlink2(76, takeoff, 1, 255, 190),
            mavlink2(77, takeoff_ack, 3),
        ]
        tracker = ProtocolStateTracker()
        for index, packet in enumerate(packets):
            evidence = mavlink_evidence(packet)
            self.assertEqual(evidence["validFrames"], 1)
            tracker.update(evidence["frames"], index)
        tracker.update(mavlink_evidence(packets[-1])["frames"], len(packets))
        result = tracker.finalize()
        self.assertEqual(result["finalState"], "takeoff-accepted")
        self.assertEqual(len(result["links"]), 2)
        self.assertEqual(result["violations"], [])
        self.assertEqual(result["ignoredDuplicateFrames"], 1)

    def test_protocol_state_reports_takeoff_without_armed_evidence_or_ack(self):
        takeoff = command_payload(22, param7=20)
        packet = mavlink2(76, takeoff, 0, 255, 190)
        tracker = ProtocolStateTracker()
        tracker.update(mavlink_evidence(packet)["frames"], 0)
        result = tracker.finalize()
        types = {item["type"] for item in result["violations"]}
        self.assertEqual(result["finalState"], "takeoff-requested")
        self.assertEqual(types, {"precondition", "missing-ack"})
        self.assertEqual(tracker.finalize()["violations"], result["violations"])

    def test_protocol_state_duplicate_memory_expires_before_sequence_wrap(self):
        heartbeat = bytearray(9)
        frame = mavlink_evidence(mavlink2(0, heartbeat, 0))["frames"]
        tracker = ProtocolStateTracker()
        tracker.update(frame, 0)
        tracker.update([], 1)
        tracker.update([], 2)
        tracker.update(frame, 3)
        result = tracker.finalize()
        self.assertEqual(result["ignoredDuplicateFrames"], 0)

    def test_full_rf_trajectory_reaches_takeoff_accepted(self):
        samples, truth = synthesize_trajectory()
        config = CaptureConfig(
            center_frequency=433_920_000,
            sample_rate=truth["sampleRate"],
            duration_seconds=samples.size / truth["sampleRate"],
            chunk_samples=710,
            ring_samples=truth["windowSamples"],
        )
        report = run_streaming(
            ArraySource(samples, truth["sampleRate"]),
            config,
            [800, 1_200, 2_400],
            analysis_window_samples=truth["windowSamples"],
            hop_samples=truth["windowSamples"],
            queue_capacity=2,
        )
        state = report["analysis"]["protocolState"]
        self.assertEqual(report["analysis"]["validProtocolWindows"], truth["windows"])
        self.assertEqual(state["finalState"], truth["expectedFinalState"])
        self.assertEqual(len(state["links"]), 2)
        self.assertEqual(state["violations"], [])

    def test_ci16_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "ci16"
            Path(str(base) + ".sigmf-meta").write_text(json.dumps({"global": {"core:datatype": "ci16_le", "core:sample_rate": 1_000}, "captures": [{"core:sample_start": 0}]}), encoding="utf-8")
            np.array([32767, 0, 0, -32768], dtype="<i2").tofile(Path(str(base) + ".sigmf-data"))
            capture = load(base)
            self.assertEqual(capture.samples.size, 2)
            self.assertAlmostEqual(float(capture.samples[0].real), 32767 / 32768)
            self.assertAlmostEqual(float(capture.samples[1].imag), -1)

    def test_ring_and_replay_capture(self):
        ring = ComplexRingBuffer(4)
        ring.write(np.array([1, 2, 3], dtype=np.complex64))
        ring.write(np.array([4, 5, 6], dtype=np.complex64))
        np.testing.assert_array_equal(ring.latest(), np.array([3, 4, 5, 6], dtype=np.complex64))
        self.assertEqual(ring.overwritten, 2)

        samples = np.arange(16, dtype=np.float32).astype(np.complex64)
        config = CaptureConfig(center_frequency=100e6, sample_rate=8, duration_seconds=2, chunk_samples=5, ring_samples=16)
        source = ArraySource(samples, 8, start_timestamp_ns=1_000, overflow_chunks={1})
        captured, report = capture(source, config)
        np.testing.assert_array_equal(captured, samples)
        self.assertTrue(report["complete"])
        self.assertEqual(report["overflows"], 1)
        self.assertEqual(report["timeouts"], 0)
        with tempfile.TemporaryDirectory() as directory:
            meta, _, stored_report = capture_to_sigmf(ArraySource(samples, 8), config, Path(directory) / "replay")
            replayed = load(meta)
            np.testing.assert_array_equal(replayed.samples, samples)
            self.assertEqual(stored_report["receivedSamples"], 16)

    def test_streaming_replay_isolates_capture_and_recovers_each_window(self):
        with tempfile.TemporaryDirectory() as directory:
            meta_path, _ = generate(Path(directory) / "stream")
            recording = load(meta_path)
            repeats = 3
            samples = np.tile(recording.samples, repeats)
            config = CaptureConfig(
                center_frequency=recording.center_frequency or 0,
                sample_rate=recording.sample_rate,
                duration_seconds=samples.size / recording.sample_rate,
                chunk_samples=731,
                ring_samples=recording.samples.size,
            )
            report = run_streaming(
                ArraySource(samples, recording.sample_rate),
                config,
                [800, 1_200, 2_400],
                analysis_window_samples=recording.samples.size,
                hop_samples=recording.samples.size,
                queue_capacity=2,
            )
            self.assertTrue(report["complete"])
            self.assertEqual(report["capture"]["receivedSamples"], samples.size)
            self.assertEqual(report["analysis"]["analyzedWindows"], repeats)
            self.assertEqual(report["analysis"]["validProtocolWindows"], repeats)
            self.assertEqual(report["analysis"]["protocolContinuity"]["duplicates"], 2)
            self.assertEqual(report["analysis"]["protocolContinuity"]["missingFrames"], 0)
            self.assertEqual(report["analysis"]["protocolState"]["finalState"], "disarmed")
            self.assertEqual(report["analysis"]["protocolState"]["ignoredDuplicateFrames"], 2)
            self.assertEqual(report["capture"]["overflows"], 0)
            self.assertIsNotNone(report["analysis"]["latencyMilliseconds"]["p95"])
            self.assertTrue(all(
                window["chosenSymbolRate"] == 1_200
                for window in report["analysis"]["windows"]
            ))

    def test_streaming_capture_failure_is_reported_without_hanging(self):
        class FailingSource:
            hardware = "failing-test-source"

            def __init__(self):
                self.stopped = False

            def configure(self, config):
                pass

            def start(self):
                pass

            def read(self, count):
                raise OSError("device disconnected")

            def stop(self):
                self.stopped = True

        source = FailingSource()
        config = CaptureConfig(
            center_frequency=100e6,
            sample_rate=48_000,
            duration_seconds=1,
        )
        with self.assertRaisesRegex(RuntimeError, "capture stage failed"):
            run_streaming(
                source,
                config,
                [1_200],
                analysis_window_samples=4_800,
            )
        self.assertTrue(source.stopped)

    def test_streaming_analysis_failure_stops_capture_thread(self):
        samples = np.ones(9_600, dtype=np.complex64)
        source = ArraySource(samples, 48_000)
        config = CaptureConfig(
            center_frequency=100e6,
            sample_rate=48_000,
            duration_seconds=samples.size / 48_000,
            chunk_samples=512,
        )
        with self.assertRaisesRegex(RuntimeError, "analysis stage failed"):
            run_streaming(
                source,
                config,
                [object()],
                analysis_window_samples=4_800,
                queue_capacity=1,
            )

    def test_operator_stop_finishes_partial_stream_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            meta_path, _ = generate(Path(directory) / "operator-stop-stream")
            recording = load(meta_path)
            stop = Event()

            class StoppingSource(ArraySource):
                def read(self, count):
                    chunk = super().read(count)
                    if self.position >= recording.samples.size:
                        stop.set()
                    return chunk

            samples = np.tile(recording.samples, 3)
            config = CaptureConfig(
                center_frequency=recording.center_frequency or 0,
                sample_rate=recording.sample_rate,
                duration_seconds=samples.size / recording.sample_rate,
                chunk_samples=740,
                ring_samples=recording.samples.size,
            )
            report = run_streaming(
                StoppingSource(samples, recording.sample_rate),
                config,
                [1_200],
                analysis_window_samples=recording.samples.size,
                stop_event=stop,
            )
            self.assertFalse(report["complete"])
            self.assertTrue(report["stoppedCleanly"])
            self.assertTrue(report["usableProtocolEvidence"])
            self.assertEqual(report["capture"]["stopReason"], "requested")
            self.assertEqual(report["capture"]["receivedSamples"], recording.samples.size)
            self.assertEqual(report["analysis"]["validProtocolWindows"], 1)


if __name__ == "__main__":
    unittest.main()

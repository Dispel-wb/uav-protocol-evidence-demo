"""Optional SoapySDR adapter. Import succeeds even when SoapySDR is absent."""
from __future__ import annotations

import numpy as np

from rf.stream_capture import CaptureConfig, StreamChunk


class SoapySource:
    def __init__(self, arguments: str = ""):
        try:
            import SoapySDR
        except ImportError as error:
            raise RuntimeError("SoapySDR Python bindings are not installed; install the driver stack for the selected SDR hardware") from error
        self.api = SoapySDR
        self.device = SoapySDR.Device(arguments)
        self.stream = None
        self.config = None
        info = self.device.getHardwareInfo()
        self.hardware = info.get("hardware", info.get("driver", "SoapySDR-device"))

    @staticmethod
    def enumerate(arguments: str = "") -> list[dict]:
        try:
            import SoapySDR
        except ImportError as error:
            raise RuntimeError("SoapySDR Python bindings are not installed") from error
        return [dict(item) for item in SoapySDR.Device.enumerate(arguments)]

    def configure(self, config: CaptureConfig) -> None:
        direction = self.api.SOAPY_SDR_RX
        self.device.setSampleRate(direction, config.channel, config.sample_rate)
        self.device.setFrequency(direction, config.channel, config.center_frequency)
        if config.bandwidth is not None:
            self.device.setBandwidth(direction, config.channel, config.bandwidth)
        if config.gain is not None:
            self.device.setGain(direction, config.channel, config.gain)
        self.stream = self.device.setupStream(direction, self.api.SOAPY_SDR_CF32, [config.channel])
        self.config = config

    def start(self) -> None:
        self.device.activateStream(self.stream)

    def read(self, count: int) -> StreamChunk:
        buffer = np.empty(count, dtype=np.complex64)
        result = self.device.readStream(self.stream, [buffer], count, timeoutUs=500_000)
        if result.ret > 0:
            return StreamChunk(buffer[:result.ret].copy(), timestamp_ns=result.timeNs if result.timeNs else None, overflow=bool(result.flags & getattr(self.api, "SOAPY_SDR_OVERFLOW", 0)))
        if result.ret == self.api.SOAPY_SDR_TIMEOUT:
            return StreamChunk(np.empty(0, dtype=np.complex64), timeout=True)
        if result.ret == self.api.SOAPY_SDR_OVERFLOW:
            return StreamChunk(np.empty(0, dtype=np.complex64), overflow=True)
        raise RuntimeError(f"SoapySDR readStream failed with code {result.ret}")

    def stop(self) -> None:
        if self.stream is not None:
            self.device.deactivateStream(self.stream)
            self.device.closeStream(self.stream)
            self.stream = None

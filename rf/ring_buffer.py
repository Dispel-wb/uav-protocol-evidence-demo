"""Fixed-size complex sample ring buffer with explicit overwrite evidence."""
from __future__ import annotations

import numpy as np


class ComplexRingBuffer:
    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self.capacity = int(capacity)
        self._data = np.zeros(self.capacity, dtype=np.complex64)
        self._write = 0
        self._size = 0
        self.overwritten = 0

    def write(self, samples: np.ndarray) -> None:
        values = np.asarray(samples, dtype=np.complex64).reshape(-1)
        if values.size >= self.capacity:
            self.overwritten += self._size + values.size - self.capacity
            self._data[:] = values[-self.capacity:]
            self._write, self._size = 0, self.capacity
            return
        overflow = max(0, self._size + values.size - self.capacity)
        self.overwritten += overflow
        first = min(values.size, self.capacity - self._write)
        self._data[self._write:self._write + first] = values[:first]
        if first < values.size:
            self._data[:values.size - first] = values[first:]
        self._write = (self._write + values.size) % self.capacity
        self._size = min(self.capacity, self._size + values.size)

    def latest(self, count: int | None = None) -> np.ndarray:
        length = self._size if count is None else min(max(0, int(count)), self._size)
        start = (self._write - length) % self.capacity
        if start + length <= self.capacity:
            return self._data[start:start + length].copy()
        first = self.capacity - start
        return np.concatenate((self._data[start:], self._data[:length - first])).copy()

    @property
    def size(self) -> int:
        return self._size

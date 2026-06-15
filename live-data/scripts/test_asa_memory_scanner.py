#!/usr/bin/env python3
"""Offline tests for asa_memory_scanner buffer helpers."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from asa_memory_scanner import find_f32_in_buffer, rescan_f32  # noqa: E402


class TestBufferScan(unittest.TestCase):
    def test_find_f32_exact(self) -> None:
        data = struct.pack("<fff", 100.0, 200.0, 100.0)
        hits = find_f32_in_buffer(data, 0x1000, 100.0, epsilon=0.01)
        self.assertEqual(hits, [0x1000, 0x1008])

    def test_find_f32_epsilon(self) -> None:
        data = struct.pack("<f", 100.02)
        hits = find_f32_in_buffer(data, 0x2000, 100.0, epsilon=0.05)
        self.assertEqual(hits, [0x2000])

    def test_find_f32_miss(self) -> None:
        data = struct.pack("<f", 42.0)
        hits = find_f32_in_buffer(data, 0x3000, 100.0, epsilon=0.01)
        self.assertEqual(hits, [])


class TestRescanMock(unittest.TestCase):
    def test_rescan_filters(self) -> None:
        class FakePM:
            def read_bytes(self, addr: int, size: int) -> bytes:
                table = {0xA: struct.pack("<f", 73.0), 0xB: struct.pack("<f", 100.0)}
                return table[addr]

        kept = rescan_f32(FakePM(), [0xA, 0xB, 0xC], 73.0, epsilon=0.01)
        self.assertEqual(kept, [0xA])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
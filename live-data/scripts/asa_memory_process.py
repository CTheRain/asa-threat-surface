"""Low-level read-only memory helpers for ArkAscended.exe (Windows)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

import pymem
import pymem.process


class MemoryReadError(RuntimeError):
    pass


@dataclass
class Vector3:
    x: float
    y: float
    z: float

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "z": self.z}


class ASAMemoryProcess:
    PROCESS_NAME = "ArkAscended.exe"
    MODULE_NAME = "ArkAscended.exe"

    def __init__(self) -> None:
        try:
            self.pm = pymem.Pymem(self.PROCESS_NAME)
        except pymem.exception.ProcessNotFound as exc:
            raise MemoryReadError("ArkAscended.exe not running") from exc
        mod = pymem.process.module_from_name(self.pm.process_handle, self.MODULE_NAME)
        if not mod:
            raise MemoryReadError(f"module not loaded: {self.MODULE_NAME}")
        self.base = mod.lpBaseOfDll
        self.module_size = mod.SizeOfImage

    def read_bytes(self, address: int, size: int) -> bytes:
        try:
            return self.pm.read_bytes(address, size)
        except Exception as exc:  # pymem raises various on bad ptr
            raise MemoryReadError(f"read_bytes failed @ 0x{address:X}") from exc

    def read_u32(self, address: int) -> int:
        return struct.unpack("<I", self.read_bytes(address, 4))[0]

    def read_u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read_bytes(address, 8))[0]

    def read_f32(self, address: int) -> float:
        return struct.unpack("<f", self.read_bytes(address, 4))[0]

    def read_ptr(self, address: int) -> int:
        return self.read_u64(address)

    def read_vector3(self, address: int) -> Vector3:
        raw = self.read_bytes(address, 12)
        x, y, z = struct.unpack("<fff", raw)
        return Vector3(x, y, z)

    def resolve_gworld(self, offsets: dict[str, Any]) -> int | None:
        gworld = offsets.get("GWorld")
        if gworld is None:
            return None
        if isinstance(gworld, str) and gworld.startswith("0x"):
            addr = int(gworld, 16)
            if addr < self.module_size:
                addr = self.base + addr
            return self.read_ptr(addr)
        if isinstance(gworld, int):
            addr = self.base + gworld if gworld < self.module_size else gworld
            return self.read_ptr(addr)
        return None

    def follow_chain(self, base: int, chain: list[int]) -> int:
        addr = base
        for i, off in enumerate(chain):
            if i < len(chain) - 1:
                addr = self.read_ptr(addr + off)
                if addr == 0:
                    raise MemoryReadError(f"null pointer in chain at offset 0x{off:X}")
            else:
                addr = addr + off
        return addr
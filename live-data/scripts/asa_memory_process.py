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

    def read_u8(self, address: int) -> int:
        return self.read_bytes(address, 1)[0]

    def read_u32(self, address: int) -> int:
        return struct.unpack("<I", self.read_bytes(address, 4))[0]

    def read_u64(self, address: int) -> int:
        return struct.unpack("<Q", self.read_bytes(address, 8))[0]

    def read_f32(self, address: int) -> float:
        return struct.unpack("<f", self.read_bytes(address, 4))[0]

    def read_ptr(self, address: int) -> int:
        return self.read_u64(address)

    def read_vector3(self, address: int, *, precision: str = "double") -> Vector3:
        """UE5 ASA FVector is 24-byte (double); legacy float path kept for probes."""
        if precision == "float":
            raw = self.read_bytes(address, 12)
            x, y, z = struct.unpack("<fff", raw)
        else:
            raw = self.read_bytes(address, 24)
            x, y, z = struct.unpack("<ddd", raw)
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

    def read_tarray_count(self, tarray_addr: int) -> int:
        """UE TArray: Num at +0x8."""
        try:
            return self.read_u32(tarray_addr + 8)
        except MemoryReadError:
            return 0

    def read_tarray_ptr(self, tarray_addr: int, index: int = 0) -> int:
        """UE TArray layout: Data* (0x0), Num (0x8), Max (0xC)."""
        data = self.read_ptr(tarray_addr)
        count = self.read_u32(tarray_addr + 8)
        if data == 0 or count == 0:
            raise MemoryReadError(f"tarray empty @ 0x{tarray_addr:X}")
        if index < 0 or index >= count:
            raise MemoryReadError(
                f"tarray index {index} out of range (count={count}) @ 0x{tarray_addr:X}"
            )
        elem = self.read_ptr(data + index * 8)
        if elem == 0:
            raise MemoryReadError(f"tarray[{index}] null @ 0x{tarray_addr:X}")
        return elem

    def follow_chain(
        self,
        base: int,
        chain: list[int],
        *,
        tarray_hops: dict[int, int] | None = None,
    ) -> int:
        """Follow pointer offsets; optional tarray_hops maps hop index -> element index."""
        addr = base
        hops = tarray_hops or {}
        for i, off in enumerate(chain):
            if i in hops:
                addr = self.read_tarray_ptr(addr + off, hops[i])
            else:
                addr = self.read_ptr(addr + off)
                if addr == 0:
                    raise MemoryReadError(f"null pointer in chain at hop {i} offset 0x{off:X}")
        return addr
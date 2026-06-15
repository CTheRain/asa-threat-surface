"""Read-only memory scanning helpers for SP offset mapping (Windows).

Uses pymem + VirtualQueryEx region walks. Never writes game memory.
"""

from __future__ import annotations

import ctypes
import struct
from dataclasses import dataclass
from typing import Iterator

import pymem
import pymem.process

MEM_COMMIT = 0x1000
MEM_FREE = 0x10000
MEM_RESERVE = 0x2000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01

READABLE_PROTECTS = {
    0x02,  # PAGE_READONLY
    0x04,  # PAGE_READWRITE
    0x08,  # PAGE_WRITECOPY
    0x20,  # PAGE_EXECUTE_READ
    0x40,  # PAGE_EXECUTE_READWRITE
    0x80,  # PAGE_EXECUTE_WRITECOPY
}

# Prefer heap-like regions first for gameplay floats.
FLOAT_SCAN_PROTECTS = {0x04, 0x40, 0x08, 0x80}

CHUNK_SIZE = 1 << 20  # 1 MiB
MAX_REGION_BYTES = 256 << 20  # skip giant regions unless forced
MAX_CANDIDATES = 50_000


class MemoryScanError(RuntimeError):
    pass


@dataclass(frozen=True)
class MemoryRegion:
    base: int
    size: int
    protect: int

    @property
    def end(self) -> int:
        return self.base + self.size


@dataclass
class PointerRef:
    holder: int
    field_offset: int

    def as_chain_tail(self) -> int:
        return self.field_offset


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", ctypes.c_ulong),
        ("RegionSize", ctypes.c_size_t),
        ("State", ctypes.c_ulong),
        ("Protect", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
    ]


def iter_regions(handle: int, *, heap_first: bool = False) -> Iterator[MemoryRegion]:
    """Walk committed readable virtual memory regions."""
    kernel32 = ctypes.windll.kernel32
    mbi = MEMORY_BASIC_INFORMATION()
    address = 0
    regions: list[MemoryRegion] = []

    while address < 0x7FFFFFFFFFFF:
        result = kernel32.VirtualQueryEx(
            handle,
            ctypes.c_void_p(address),
            ctypes.byref(mbi),
            ctypes.sizeof(mbi),
        )
        if result == 0:
            break
        base = mbi.BaseAddress or 0
        size = int(mbi.RegionSize)
        protect = int(mbi.Protect)
        if (
            mbi.State == MEM_COMMIT
            and protect in READABLE_PROTECTS
            and not (protect & PAGE_GUARD)
            and size > 0
        ):
            regions.append(MemoryRegion(base=base, size=size, protect=protect))
        address = base + size

    if heap_first:
        regions.sort(key=lambda r: (0 if r.protect in FLOAT_SCAN_PROTECTS else 1, r.size))
    return iter(regions)


def find_f32_in_buffer(
    data: bytes,
    base_address: int,
    target: float,
    *,
    epsilon: float = 0.01,
) -> list[int]:
    hits: list[int] = []
    if len(data) < 4:
        return hits
    for offset in range(0, len(data) - 3, 4):
        value = struct.unpack_from("<f", data, offset)[0]
        if abs(value - target) <= epsilon:
            hits.append(base_address + offset)
    return hits


def scan_f32(
    pm: pymem.Pymem,
    target: float,
    *,
    epsilon: float = 0.01,
    heap_first: bool = True,
    include_large_regions: bool = False,
    progress: bool = False,
) -> list[int]:
    """Scan readable regions for a float32 value."""
    candidates: list[int] = []
    handle = pm.process_handle
    scanned_bytes = 0

    for region in iter_regions(handle, heap_first=heap_first):
        if not include_large_regions and region.size > MAX_REGION_BYTES:
            continue
        if heap_first and region.protect not in FLOAT_SCAN_PROTECTS:
            continue
        offset = 0
        while offset < region.size:
            read_size = min(CHUNK_SIZE, region.size - offset)
            addr = region.base + offset
            try:
                data = pm.read_bytes(addr, read_size)
            except Exception:
                offset += read_size
                continue
            hits = find_f32_in_buffer(data, addr, target, epsilon=epsilon)
            candidates.extend(hits)
            scanned_bytes += read_size
            if len(candidates) > MAX_CANDIDATES:
                raise MemoryScanError(
                    f"too many candidates ({len(candidates)}); change the value more or tighten epsilon"
                )
            if progress and scanned_bytes and scanned_bytes % (16 << 20) == 0:
                print(f"  scanned {scanned_bytes // (1 << 20)} MiB, candidates={len(candidates)}", flush=True)
            offset += read_size

    return candidates


def rescan_f32(
    pm: pymem.Pymem,
    addresses: list[int],
    target: float,
    *,
    epsilon: float = 0.01,
) -> list[int]:
    """Re-read candidate addresses and keep those still matching target."""
    kept: list[int] = []
    for addr in addresses:
        try:
            raw = pm.read_bytes(addr, 4)
            value = struct.unpack("<f", raw)[0]
        except Exception:
            continue
        if abs(value - target) <= epsilon:
            kept.append(addr)
    return kept


def read_f32_at(pm: pymem.Pymem, address: int) -> float | None:
    try:
        return struct.unpack("<f", pm.read_bytes(address, 4))[0]
    except Exception:
        return None


def find_pointers_to(
    pm: pymem.Pymem,
    target: int,
    *,
    max_field_offset: int = 0x2000,
    field_step: int = 8,
    module_base: int | None = None,
    module_size: int | None = None,
    limit: int = 200,
) -> list[PointerRef]:
    """Find addresses holding a pointer that reaches target (+ field offset)."""
    refs: list[PointerRef] = []
    handle = pm.process_handle
    seen: set[tuple[int, int]] = set()

    for region in iter_regions(handle):
        if module_base is not None and module_size is not None:
            in_module = region.base >= module_base and region.end <= module_base + module_size
            heap_like = region.protect in FLOAT_SCAN_PROTECTS
            if not (in_module or heap_like):
                continue
        offset = 0
        while offset < region.size:
            read_size = min(CHUNK_SIZE, region.size - offset)
            addr = region.base + offset
            try:
                data = pm.read_bytes(addr, read_size)
            except Exception:
                offset += read_size
                continue
            for rel in range(0, len(data) - 7, 8):
                ptr = struct.unpack_from("<Q", data, rel)[0]
                if ptr < 0x10000 or ptr > 0x7FFFFFFFFFFF:
                    continue
                holder = addr + rel
                for field_off in range(0, max_field_offset + 1, field_step):
                    if ptr + field_off != target:
                        continue
                    key = (holder, field_off)
                    if key in seen:
                        continue
                    seen.add(key)
                    refs.append(PointerRef(holder=holder, field_offset=field_off))
                    if len(refs) >= limit:
                        return refs
            offset += read_size
    return refs


def resolve_module(pm: pymem.Pymem, name: str = "ArkAscended.exe") -> tuple[int, int]:
    mod = pymem.process.module_from_name(pm.process_handle, name)
    if not mod:
        raise MemoryScanError(f"module not loaded: {name}")
    return mod.lpBaseOfDll, mod.SizeOfImage


def attach(process_name: str = "ArkAscended.exe") -> pymem.Pymem:
    try:
        return pymem.Pymem(process_name)
    except pymem.exception.ProcessNotFound as exc:
        raise MemoryScanError(f"{process_name} not running") from exc


def build_chain_from_ref(
    pm: pymem.Pymem,
    ref: PointerRef,
    *,
    module_base: int,
    max_depth: int = 4,
) -> list[str] | None:
    """Try to extend a pointer ref into a static module-relative chain."""
    chain: list[int] = [ref.field_offset]
    current = ref.holder
    depth = 0
    while depth < max_depth:
        parents = find_pointers_to(pm, current, max_field_offset=0x800, field_step=8, limit=20)
        static = [p for p in parents if module_base <= p.holder < module_base + (1 << 28)]
        if not static:
            break
        parent = static[0]
        chain.insert(0, parent.holder - module_base)
        current = parent.holder
        depth += 1
    if not chain:
        return None
    return [hex(x) if isinstance(x, int) else x for x in chain]
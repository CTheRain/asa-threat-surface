#!/usr/bin/env python3
"""Live shoulder-creature probe — SP lab only.

Reads pawn attach graph + MountedDino weak ptr variants to find spawned shoulder pets
(e.g. Gloon / LostCharge_LanternPet_Char_BP_C) that never appear in inventory TArray.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from asa_memory_process import ASAMemoryProcess, MemoryReadError, Vector3
from asa_memory_reader import (
    DEFAULT_OFFSETS,
    _chain_cfg,
    _is_plausible_game_ptr,
    _parse_off,
    _resolve_chain,
    load_offsets,
)
from asa_sp_gate import verify_singleplayer
from asa_state_decoder import decode_shoulder_mount_state

# APrimalCharacter / APrimalDinoCharacter (GObjects-Dump-WithProperties.txt)
PAWN_SHOULDER_FIELDS = {
    "mounted_dino_weak": 0x1160,
    "carried_character_weak": 0x2258,
    "b_is_carried_as_passenger": 0x16CB,
}
SCENE_ATTACH_CHILDREN = 0xE8
ACTOR_ROOT_COMPONENT = 0x398
SCENE_RELATIVE_LOCATION = 0x148
UOBJECT_CLASS = 0x10
UOBJECT_NAME = 0x18
UOBJECT_OUTER = 0x28
SCENE_ATTACH_SOCKET = 0xD8

SHOULDER_CLASS_HINTS = (
    "LostCharge_LanternPet",
    "LanternPet",
    "DinoCompanion",
    "ShoulderDragon",
)


def _fmt_ptr(ptr: int | None) -> str | None:
    return f"0x{ptr:X}" if ptr else None


def _read_weak_candidates(mem: ASAMemoryProcess, base: int, off: int) -> dict[str, Any]:
    raw = mem.read_bytes(base + off, 16)
    u64 = int.from_bytes(raw[0:8], "little")
    u32a = int.from_bytes(raw[0:4], "little", signed=True)
    u32b = int.from_bytes(raw[4:8], "little", signed=True)
    u64b = int.from_bytes(raw[8:16], "little") if len(raw) >= 16 else 0
    candidates: dict[str, Any] = {
        "offset": f"0x{off:X}",
        "raw_hex": raw.hex(),
        "as_u64": _fmt_ptr(u64 if _is_plausible_game_ptr(u64) else None),
        "as_index_serial": {"index": u32a, "serial": u32b},
        "as_u64_alt8": _fmt_ptr(u64b if _is_plausible_game_ptr(u64b) else None),
    }
    return candidates


def _read_bit(mem: ASAMemoryProcess, base: int, byte_off: int, bit: int) -> bool | None:
    try:
        val = mem.read_u8(base + byte_off)
        return bool((val >> bit) & 1)
    except MemoryReadError:
        return None


def _actor_position(mem: ASAMemoryProcess, actor_ptr: int) -> dict[str, float] | None:
    try:
        root = mem.read_ptr(actor_ptr + ACTOR_ROOT_COMPONENT)
        if not _is_plausible_game_ptr(root):
            return None
        loc = mem.read_vector3(root + SCENE_RELATIVE_LOCATION)
        return loc.as_dict()
    except MemoryReadError:
        return None


def _fname_string(mem: ASAMemoryProcess, fname_addr: int) -> str | None:
    """Best-effort FName -> not resolved without GNames; return numeric index."""
    try:
        idx = mem.read_u32(fname_addr)
        return f"FName#{idx}"
    except MemoryReadError:
        return None


def _looks_like_actor(mem: ASAMemoryProcess, obj_ptr: int) -> bool:
    if not _is_plausible_game_ptr(obj_ptr):
        return False
    try:
        root = mem.read_ptr(obj_ptr + ACTOR_ROOT_COMPONENT)
    except MemoryReadError:
        return False
    if not _is_plausible_game_ptr(root):
        return False
    try:
        loc = mem.read_vector3(root + SCENE_RELATIVE_LOCATION)
    except MemoryReadError:
        return False
    for axis in (loc.x, loc.y, loc.z):
        if abs(axis) > 5e8 or (axis != 0.0 and abs(axis) < 1e-30):
            return False
    return True


def _resolve_outer_actor(mem: ASAMemoryProcess, obj_ptr: int, *, max_hops: int = 10) -> int | None:
    current = obj_ptr
    for _ in range(max_hops):
        if not _is_plausible_game_ptr(current):
            return None
        if _looks_like_actor(mem, current):
            return current
        try:
            current = mem.read_ptr(current + UOBJECT_OUTER)
        except MemoryReadError:
            return None
    return None


def _object_label(mem: ASAMemoryProcess, obj_ptr: int) -> dict[str, Any]:
    out: dict[str, Any] = {"ptr": _fmt_ptr(obj_ptr)}
    try:
        cls = mem.read_ptr(obj_ptr + UOBJECT_CLASS)
        if _is_plausible_game_ptr(cls):
            out["class_ptr"] = _fmt_ptr(cls)
            out["class_name_hint"] = _fname_string(mem, cls + UOBJECT_NAME)
        out["object_name_hint"] = _fname_string(mem, obj_ptr + UOBJECT_NAME)
    except MemoryReadError:
        out["label_error"] = "name_read_failed"
    pos = _actor_position(mem, obj_ptr)
    if pos:
        out["relative_position"] = pos
    return out


def _distance(a: dict[str, float], b: dict[str, float]) -> float | None:
    try:
        dx = float(a["x"]) - float(b["x"])
        dy = float(a["y"]) - float(b["y"])
        dz = float(a["z"]) - float(b["z"])
        if max(abs(dx), abs(dy), abs(dz)) > 1e9:
            return None
        return (dx * dx + dy * dy + dz * dz) ** 0.5
    except (OverflowError, TypeError, ValueError):
        return None


def _read_attach_children(
    mem: ASAMemoryProcess, scene_ptr: int, *, max_children: int = 12
) -> list[dict[str, Any]]:
    children: list[dict[str, Any]] = []
    try:
        count = mem.read_tarray_count(scene_ptr + SCENE_ATTACH_CHILDREN)
        data = mem.read_ptr(scene_ptr + SCENE_ATTACH_CHILDREN)
    except MemoryReadError:
        return children
    if not _is_plausible_game_ptr(data) or count <= 0:
        return children
    for idx in range(min(count, max_children)):
        try:
            child_scene = mem.read_ptr(data + idx * 8)
        except MemoryReadError:
            continue
        if not _is_plausible_game_ptr(child_scene):
            continue
        entry: dict[str, Any] = {
            "index": idx,
            "scene_component_ptr": _fmt_ptr(child_scene),
        }
        try:
            attach_parent = mem.read_ptr(child_scene + 0xD0)
            if _is_plausible_game_ptr(attach_parent):
                entry["attach_parent_ptr"] = _fmt_ptr(attach_parent)
        except MemoryReadError:
            pass
        try:
            sock_idx = mem.read_u32(child_scene + SCENE_ATTACH_SOCKET)
            entry["attach_socket_fname"] = f"FName#{sock_idx}"
        except MemoryReadError:
            pass
        actor_ptr = _resolve_outer_actor(mem, child_scene)
        if actor_ptr:
            entry["owner_actor"] = _object_label(mem, actor_ptr)
        children.append(entry)
    return children


def _scan_pawn_ptr_window(mem: ASAMemoryProcess, pawn_ptr: int) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for off in range(0x1100, 0x1280, 8):
        try:
            ptr = mem.read_ptr(pawn_ptr + off)
        except MemoryReadError:
            continue
        if not _is_plausible_game_ptr(ptr):
            continue
        label = _object_label(mem, ptr)
        name_blob = json.dumps(label).lower()
        if any(hint.lower() in name_blob for hint in SHOULDER_CLASS_HINTS):
            hits.append({"offset": f"0x{off:X}", **label})
    return hits


def probe(offsets_path: Path) -> dict[str, Any]:
    gate = verify_singleplayer()
    if not gate.ok:
        raise SystemExit(f"SP gate blocked: {gate.reasons}")

    offsets = load_offsets(offsets_path)
    mem = ASAMemoryProcess()
    gworld = mem.resolve_gworld(offsets)
    if not gworld:
        raise SystemExit("GWorld unresolved")

    pawn_ptr = _resolve_chain(mem, gworld, "local_player_pawn", offsets)
    if not pawn_ptr:
        raise SystemExit("pawn chain failed")

    player_pos = _actor_position(mem, pawn_ptr)
    root_ptr = None
    try:
        root_ptr = mem.read_ptr(pawn_ptr + ACTOR_ROOT_COMPONENT)
    except MemoryReadError:
        pass

    result: dict[str, Any] = {
        "schema": "ark_sp_shoulder_probe.v0.1",
        "pawn_ptr": _fmt_ptr(pawn_ptr),
        "player_position": player_pos,
        "root_component_ptr": _fmt_ptr(root_ptr) if _is_plausible_game_ptr(root_ptr) else None,
        "weak_fields": {
            name: _read_weak_candidates(mem, pawn_ptr, off)
            for name, off in PAWN_SHOULDER_FIELDS.items()
            if name.endswith("_weak")
        },
        "flags": {
            "b_is_carried_as_passenger_bit0": _read_bit(
                mem, pawn_ptr, PAWN_SHOULDER_FIELDS["b_is_carried_as_passenger"], 0
            ),
        },
        "attach_children": _read_attach_children(mem, root_ptr) if root_ptr else [],
        "ptr_window_hits": _scan_pawn_ptr_window(mem, pawn_ptr),
        "nearby_shoulder_candidates": [],
    }

    mounted_raw = result["weak_fields"].get("mounted_dino_weak", {})
    for key in ("as_u64", "as_u64_alt8"):
        ptr_hex = mounted_raw.get(key)
        if not ptr_hex:
            continue
        ptr = int(ptr_hex, 16)
        label = _object_label(mem, ptr)
        label["source"] = f"mounted_dino_weak.{key}"
        if player_pos and label.get("relative_position"):
            dist = _distance(player_pos, label["relative_position"])
            if dist is not None:
                label["distance_to_player"] = round(dist, 2)
        result["nearby_shoulder_candidates"].append(label)

    for child in result["attach_children"]:
        owner = child.get("owner_actor")
        if not owner:
            continue
        if player_pos and owner.get("relative_position"):
            dist = _distance(player_pos, owner["relative_position"])
            if dist is not None:
                owner["distance_to_player"] = round(dist, 2)
        name_blob = json.dumps(owner).lower()
        dist_ok = owner.get("distance_to_player")
        if any(h in name_blob for h in SHOULDER_CLASS_HINTS) or (
            isinstance(dist_ok, (int, float)) and dist_ok < 500
        ):
            result["nearby_shoulder_candidates"].append(
                {"source": "attach_children", **owner}
            )

    mounted = result["weak_fields"].get("mounted_dino_weak", {})
    idx = (mounted.get("as_index_serial") or {}).get("index")
    serial = (mounted.get("as_index_serial") or {}).get("serial")
    if isinstance(idx, int) and idx > 0:
        result["mounted_dino_gobject_index"] = idx
        result["mounted_dino_gobject_index_hex"] = f"0x{idx:X}"
    attach_ptrs = [
        c.get("scene_component_ptr")
        for c in result.get("attach_children") or []
        if c.get("scene_component_ptr")
    ]
    shoulder_snap = {
        "mounted_dino_weak_index": idx,
        "mounted_dino_weak_serial": serial,
        "attach_child_count": len(attach_ptrs),
        "attach_child_ptrs": attach_ptrs,
    }
    result["shoulder_mount"] = decode_shoulder_mount_state(shoulder_snap)
    mount_state = result["shoulder_mount"].get("mount_state")
    class_hit = len(result["nearby_shoulder_candidates"]) > 0
    result["has_shoulder_creature"] = class_hit or mount_state in (
        "mounted",
        "grounded",
        "transition",
    )
    result["notes"] = [
        "MountedDino @ pawn+0x1160 is FWeakObjectPtr (index+serial), not a raw UObject*.",
        "Inventory TArray Pet/Costume rows do not cover shoulder lantern pets (Gloon).",
        "Gloon class_ref: LostCharge_LanternPet_Char_BP_C; tribe log display: Gloon.",
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe shoulder-mounted creature (SP lab)")
    parser.add_argument("--offsets", type=Path, default=DEFAULT_OFFSETS)
    parser.add_argument("--out", type=Path, default=None, help="Write JSON to path")
    args = parser.parse_args()
    report = probe(args.offsets)
    text = json.dumps(report, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
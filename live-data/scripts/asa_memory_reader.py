#!/usr/bin/env python3
"""Read-only ARK: Survival Ascended memory digest — SINGLEPLAYER ONLY.

Writes memory_digest.json and appends memory_stream.jsonl under ARK_LIVE_DATA.
Does not write game memory. Refuses dedicated/multiplayer sessions and BattlEye-on play.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from asa_memory_process import ASAMemoryProcess, MemoryReadError
from asa_sp_gate import GateResult, SingleplayerGateError, verify_singleplayer
from asa_state_decoder import SHOULDER_ATTACH_BASELINE, decode_snapshot

DEFAULT_OUT_DIR = SCRIPT_DIR.parent
OUT_DIR = Path(os.environ.get("ARK_LIVE_DATA", DEFAULT_OUT_DIR))
DIGEST_FILE = OUT_DIR / "memory_digest.json"
STREAM_FILE = OUT_DIR / "memory_stream.jsonl"
TEMPLATE_OFFSETS = SCRIPT_DIR.parent / "templates" / "memory_offsets.template.json"
DEFAULT_OFFSETS = OUT_DIR / "config" / "memory_offsets.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_output_dir(path: Path) -> None:
    global OUT_DIR, DIGEST_FILE, STREAM_FILE, DEFAULT_OFFSETS
    OUT_DIR = path
    DIGEST_FILE = OUT_DIR / "memory_digest.json"
    STREAM_FILE = OUT_DIR / "memory_stream.jsonl"
    DEFAULT_OFFSETS = OUT_DIR / "config" / "memory_offsets.json"


def load_offsets(path: Path) -> dict:
    if not path.exists():
        if TEMPLATE_OFFSETS.exists():
            return json.loads(TEMPLATE_OFFSETS.read_text(encoding="utf-8"))
        return {"GWorld": None, "chains": {}, "fields": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_off(value: str | int | None) -> int | None:
    if value is None:
        return None
    return int(value, 16) if isinstance(value, str) else int(value)


def _chain_cfg(offsets: dict, name: str) -> tuple[list[int], dict[int, int]]:
    raw = offsets.get("chains", {}).get(name) or []
    if isinstance(raw, dict):
        chain = [_parse_off(x) for x in raw.get("offsets") or []]
        tarray = {int(k): int(v) for k, v in (raw.get("tarray_at") or {}).items()}
        return [x for x in chain if x is not None], tarray
    return [_parse_off(x) for x in raw if _parse_off(x) is not None], {}


def _resolve_chain(
    mem: ASAMemoryProcess,
    base: int,
    chain_name: str,
    offsets: dict,
) -> int | None:
    chain, tarray = _chain_cfg(offsets, chain_name)
    if not chain:
        return None
    try:
        return mem.follow_chain(base, chain, tarray_hops=tarray)
    except MemoryReadError:
        return None


def _read_field_f32(mem: ASAMemoryProcess, base: int, field_off: str | int | None) -> float | None:
    off = _parse_off(field_off)
    if off is None:
        return None
    try:
        return mem.read_f32(base + off)
    except MemoryReadError:
        return None


def _read_field_ptr(mem: ASAMemoryProcess, base: int, field_off: str | int | None) -> int | None:
    off = _parse_off(field_off)
    if off is None:
        return None
    try:
        ptr = mem.read_ptr(base + off)
        return ptr or None
    except MemoryReadError:
        return None


def _read_weak_ptr(mem: ASAMemoryProcess, base: int, field_off: str | int | None) -> int | None:
    """TWeakObjectPtr — object pointer at +0; reject packed serial garbage."""
    ptr = _read_field_ptr(mem, base, field_off)
    return ptr if _is_plausible_game_ptr(ptr) else None


def _read_weak_index_serial(
    mem: ASAMemoryProcess, base: int, field_off: str | int | None
) -> tuple[int | None, int | None]:
    off = _parse_off(field_off)
    if off is None:
        return None, None
    try:
        raw = mem.read_bytes(base + off, 8)
        idx = int.from_bytes(raw[0:4], "little", signed=True)
        serial = int.from_bytes(raw[4:8], "little", signed=True)
        return idx, serial
    except MemoryReadError:
        return None, None


def _read_shoulder_attach_snapshot(
    mem: ASAMemoryProcess, pawn_ptr: int, fields: dict
) -> tuple[dict[str, Any], list[str]]:
    limits: list[str] = []
    shoulder: dict[str, Any] = {
        "attach_baseline_count": SHOULDER_ATTACH_BASELINE,
    }

    idx, serial = _read_weak_index_serial(mem, pawn_ptr, fields.get("mounted_dino"))
    shoulder["mounted_dino_weak_index"] = idx
    shoulder["mounted_dino_weak_serial"] = serial
    if idx is None:
        limits.append("shoulder_mounted_dino_weak_read_failed")

    root_off = _parse_off(fields.get("root_component"))
    if root_off is None:
        limits.append("shoulder_root_component_offset_missing")
        return shoulder, limits

    try:
        root_ptr = mem.read_ptr(pawn_ptr + root_off)
    except MemoryReadError:
        limits.append("shoulder_root_component_read_failed")
        return shoulder, limits

    if not _is_plausible_game_ptr(root_ptr):
        limits.append("shoulder_root_component_null")
        return shoulder, limits

    shoulder["root_component_ptr"] = _fmt_ptr(root_ptr)
    attach_off = 0xE8
    try:
        count = mem.read_tarray_count(root_ptr + attach_off)
        data = mem.read_ptr(root_ptr + attach_off)
    except MemoryReadError:
        limits.append("shoulder_attach_children_read_failed")
        return shoulder, limits

    ptrs: list[str] = []
    if _is_plausible_game_ptr(data) and count > 0:
        for i in range(min(count, 12)):
            try:
                child_scene = mem.read_ptr(data + i * 8)
            except MemoryReadError:
                continue
            if _is_plausible_game_ptr(child_scene):
                ptrs.append(_fmt_ptr(child_scene) or "?")

    shoulder["attach_child_count"] = len(ptrs) if ptrs else count
    shoulder["attach_child_ptrs"] = ptrs
    return shoulder, limits


def _read_dino_mount_snapshot(
    mem: ASAMemoryProcess, pawn_ptr: int, fields: dict
) -> tuple[dict[str, Any], list[str]]:
    limits: list[str] = []
    mount: dict[str, Any] = {}

    idx, serial = _read_weak_index_serial(mem, pawn_ptr, fields.get("rider"))
    mount["rider_weak_index"] = idx
    mount["rider_weak_serial"] = serial
    if idx is None:
        limits.append("dino_rider_weak_read_failed")

    mount["has_rider"] = isinstance(idx, int) and idx > 0
    mount["controlling_saddled_dino"] = mount["has_rider"]
    mount["pawn_control_mode"] = "dino_pawn" if mount["has_rider"] else "human_pawn"
    if mount["has_rider"]:
        mount["rider_weak_index_hex"] = f"0x{idx:X}"

    return mount, limits


def _read_owl_abilities_snapshot(
    mem: ASAMemoryProcess,
    pawn_ptr: int,
    offsets: dict,
    *,
    dino_mount: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Snow Owl class-specific ability flags — only valid on dino pawn (has_rider)."""
    limits: list[str] = []
    snap: dict[str, Any] = {"class_ref": "Owl_Character_BP_C"}

    if not dino_mount or not dino_mount.get("has_rider"):
        snap["applicable"] = False
        limits.append("owl_abilities_not_applicable")
        return snap, limits

    snap["applicable"] = True
    owl_fields = offsets.get("owl_class_fields") or {}
    for key in ("encapsulate_is_active", "ice_crash_is_active"):
        spec = owl_fields.get(key)
        if not isinstance(spec, dict):
            limits.append(f"owl_{key}_offset_missing")
            continue
        val = _read_bit_bool(mem, pawn_ptr, spec.get("offset"), int(spec.get("bit", 0)))
        snap[key] = val
        if val is None:
            limits.append(f"owl_{key}_read_failed")

    return snap, limits


def _fmt_ptr(ptr: int | None) -> str | None:
    return f"0x{ptr:X}" if ptr else None


def _is_plausible_game_ptr(ptr: int | None) -> bool:
    if not ptr:
        return False
    if ptr in (0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF, 0x7FFFFFFFFFFFFFFF):
        return False
    if ptr & 7:
        return False
    if ptr >= 0x7FF000000000:
        return False
    return 0x10000 <= ptr <= 0x7FFFFFFFFFFF


def _read_bit_bool(mem: ASAMemoryProcess, base: int, byte_off: str | int, bit: int) -> bool | None:
    off = _parse_off(byte_off)
    if off is None:
        return None
    try:
        val = mem.read_u8(base + off)
        return bool((val >> bit) & 1)
    except MemoryReadError:
        return None


def _read_bool_field(mem: ASAMemoryProcess, base: int, field_off: str | int | None) -> bool | None:
    off = _parse_off(field_off)
    if off is None:
        return None
    try:
        return bool(mem.read_u8(base + off))
    except MemoryReadError:
        return None


def _read_mission_state(
    mem: ASAMemoryProcess,
    pc_ptr: int | None,
    paths: dict,
) -> tuple[dict[str, Any], list[str]]:
    """Controller -> ShooterHUD -> mission widget -> MissionData buff -> AMissionType."""
    state: dict[str, Any] = {}
    limits: list[str] = []
    if not pc_ptr:
        limits.append("mission_no_player_controller")
        return state, limits

    def hop(base: int | None, key: str) -> int | None:
        if not base:
            return None
        off = _parse_off(paths.get(key))
        if off is None:
            limits.append(f"mission_path_missing:{key}")
            return None
        return _read_field_ptr(mem, base, off)

    hud = hop(pc_ptr, "my_hud")
    state["my_hud"] = _fmt_ptr(hud)
    if not hud:
        limits.append("mission_my_hud_null")
        return state, limits

    mission_hud = hop(hud, "active_mission_hud")
    state["active_mission_hud"] = _fmt_ptr(mission_hud)
    if not mission_hud:
        limits.append("mission_hud_widget_null")
        return state, limits

    widget_mission = hop(mission_hud, "widget_active_mission")
    mission_data = hop(mission_hud, "widget_mission_data")
    state["widget_active_mission"] = _fmt_ptr(widget_mission)
    state["mission_data_buff"] = _fmt_ptr(mission_data)

    active_mission = None
    if mission_data:
        active_mission = hop(mission_data, "md_active_mission")
        idx_off = _parse_off(paths.get("md_active_mission_index"))
        if idx_off is not None:
            try:
                state["active_mission_index"] = mem.read_u32(mission_data + idx_off)
            except MemoryReadError:
                limits.append("mission_index_read_failed")
        tarray_off = _parse_off(paths.get("md_current_missions"))
        if tarray_off is not None:
            state["current_missions_count"] = mem.read_tarray_count(mission_data + tarray_off)
        movie_off = _parse_off(paths.get("md_playing_mission_movie"))
        if movie_off is not None:
            try:
                state["playing_mission_movie"] = bool(mem.read_u8(mission_data + movie_off))
            except MemoryReadError:
                limits.append("mission_movie_flag_read_failed")
    if not active_mission:
        active_mission = widget_mission

    state["active_mission"] = _fmt_ptr(active_mission)
    if not active_mission:
        return state, limits

    state_off = _parse_off(paths.get("mt_mission_state"))
    if state_off is not None:
        try:
            state["mission_state_raw"] = mem.read_u8(active_mission + state_off)
        except MemoryReadError:
            limits.append("mission_state_read_failed")

    return state, limits


def _read_inventory_item_array(
    mem: ASAMemoryProcess,
    inv_ptr: int,
    array_off: int,
    *,
    slot_prefix: str,
    inventory_fields: dict,
    max_slots: int = 24,
) -> tuple[list[dict[str, Any]], list[str]]:
    limits: list[str] = []
    slots: list[dict[str, Any]] = []

    type_off = _parse_off(inventory_fields.get("item_my_equipment_type"))
    chibi_level_off = _parse_off(inventory_fields.get("item_chibi_level"))
    chibi_ctrl_off = _parse_off(inventory_fields.get("item_chibi_controller"))
    flag_spec = inventory_fields.get("item_equipped_flag") or {}
    flag_off = _parse_off(flag_spec.get("offset"))
    flag_bit = int(flag_spec.get("bit", 5))

    try:
        item_count = mem.read_tarray_count(inv_ptr + array_off)
    except MemoryReadError:
        limits.append(f"{slot_prefix}_count_failed")
        return slots, limits

    if item_count <= 0:
        return slots, limits

    try:
        data_ptr = mem.read_ptr(inv_ptr + array_off)
        read_count = min(item_count, max_slots)
        for idx in range(read_count):
            try:
                item_ptr = mem.read_ptr(data_ptr + idx * 8)
            except MemoryReadError:
                limits.append(f"{slot_prefix}_{idx}_ptr_failed")
                continue
            slot: dict[str, Any] = {
                "index": idx,
                "item_ptr": _fmt_ptr(item_ptr),
            }
            if item_ptr and type_off is not None:
                try:
                    slot["equipment_type_id"] = mem.read_u8(item_ptr + type_off)
                except MemoryReadError:
                    limits.append(f"{slot_prefix}_{idx}_type_failed")
            if item_ptr and flag_off is not None:
                slot["is_equipped_flag"] = _read_bit_bool(mem, item_ptr, flag_off, flag_bit)
            if item_ptr and chibi_level_off is not None:
                try:
                    slot["chibi_level"] = mem.read_u32(item_ptr + chibi_level_off)
                except MemoryReadError:
                    limits.append(f"{slot_prefix}_{idx}_chibi_level_failed")
            if item_ptr and chibi_ctrl_off is not None:
                try:
                    ctrl_ptr = mem.read_ptr(item_ptr + chibi_ctrl_off)
                    slot["chibi_controller_ptr"] = (
                        _fmt_ptr(ctrl_ptr) if _is_plausible_game_ptr(ctrl_ptr) else None
                    )
                except MemoryReadError:
                    limits.append(f"{slot_prefix}_{idx}_chibi_controller_failed")
            slots.append(slot)
        if item_count > max_slots:
            limits.append(f"{slot_prefix}_truncated")
    except MemoryReadError:
        limits.append(f"{slot_prefix}_read_failed")

    return slots, limits


def _read_equipped_items(
    mem: ASAMemoryProcess,
    inv_ptr: int | None,
    inventory_fields: dict,
    *,
    max_slots: int = 24,
) -> tuple[dict[str, Any], list[str]]:
    state: dict[str, Any] = {}
    limits: list[str] = []
    if not inv_ptr:
        limits.append("equipment_no_inventory_component")
        return state, limits

    state["inventory_component"] = _fmt_ptr(inv_ptr)

    inv_items_off = _parse_off(inventory_fields.get("inventory_items"))
    if inv_items_off is not None:
        state["inventory_item_count"] = mem.read_tarray_count(inv_ptr + inv_items_off)

    equipped_off = _parse_off(inventory_fields.get("equipped_items"))
    if equipped_off is None:
        limits.append("equipment_equipped_items_offset_missing")
    else:
        state["equipped_count"] = mem.read_tarray_count(inv_ptr + equipped_off)
        equipped_slots, equipped_limits = _read_inventory_item_array(
            mem,
            inv_ptr,
            equipped_off,
            slot_prefix="equipment_slot",
            inventory_fields=inventory_fields,
            max_slots=max_slots,
        )
        state["equipped_slots"] = equipped_slots
        limits.extend(equipped_limits)

    item_slots_off = _parse_off(inventory_fields.get("item_slots"))
    if item_slots_off is not None:
        state["item_slot_count"] = mem.read_tarray_count(inv_ptr + item_slots_off)
        item_slots, slot_limits = _read_inventory_item_array(
            mem,
            inv_ptr,
            item_slots_off,
            slot_prefix="item_slot",
            inventory_fields=inventory_fields,
            max_slots=max_slots,
        )
        state["item_slots"] = item_slots
        limits.extend(slot_limits)

    return state, limits


def _read_movement_state(
    mem: ASAMemoryProcess,
    pawn_ptr: int | None,
    fields: dict,
) -> tuple[dict[str, Any], list[str]]:
    state: dict[str, Any] = {}
    limits: list[str] = []
    if not pawn_ptr:
        limits.append("movement_no_pawn")
        return state, limits

    movement_ptr = _read_field_ptr(mem, pawn_ptr, fields.get("character_movement"))
    state["character_movement_ptr"] = _fmt_ptr(movement_ptr)
    if not movement_ptr:
        limits.append("movement_component_null")
        return state, limits

    mode_off = _parse_off(fields.get("movement_mode"))
    custom_off = _parse_off(fields.get("custom_movement_mode"))
    if mode_off is not None:
        try:
            state["movement_mode_raw"] = mem.read_u8(movement_ptr + mode_off)
        except MemoryReadError:
            limits.append("movement_mode_read_failed")
    if custom_off is not None:
        try:
            state["custom_movement_mode"] = mem.read_u8(movement_ptr + custom_off)
        except MemoryReadError:
            limits.append("movement_custom_mode_read_failed")

    return state, limits


def _sanitize_world_float(key: str, val: float) -> float | None:
    if key == "day_time" and (val < 0 or val > 86400.0 * 365.0):
        return None
    if key == "night_time_speed_scale" and (val < 0.01 or val > 50.0):
        return None
    if key == "server_world_time_seconds_delta" and abs(val) > 1e9:
        return None
    return val


def read_state_snapshot(mem: ASAMemoryProcess, offsets: dict) -> dict:
    limits: list[str] = []
    state: dict[str, Any] = {
        "pointers": {},
        "session": {},
        "player": {},
        "controller": {},
        "mission": {},
        "equipment": {},
        "movement": {},
        "shoulder": {},
        "dino_mount": {},
        "owl_abilities": {},
        "world": {},
        "status": {},
    }

    gworld_ptr = mem.resolve_gworld(offsets)
    state["pointers"]["gworld"] = f"0x{gworld_ptr:X}" if gworld_ptr else None
    if not gworld_ptr:
        limits.append("gworld_offset_missing")
        return {"state": state, "limits": limits}

    fields = offsets.get("fields", {})

    for key in ("net_driver", "demo_net_driver", "authority_game_mode"):
        ptr = _read_field_ptr(mem, gworld_ptr, fields.get(key))
        state["session"][key] = _fmt_ptr(ptr)

    pc_ptr = _resolve_chain(mem, gworld_ptr, "local_player_controller", offsets)
    state["pointers"]["player_controller"] = _fmt_ptr(pc_ptr)
    if not pc_ptr:
        limits.append("player_controller_chain_failed")

    pawn_ptr = _resolve_chain(mem, gworld_ptr, "local_player_pawn", offsets)
    state["pointers"]["pawn"] = f"0x{pawn_ptr:X}" if pawn_ptr else None
    if not pawn_ptr:
        limits.append("pawn_chain_failed")

    gs_ptr = _resolve_chain(mem, gworld_ptr, "game_state", offsets)
    state["pointers"]["game_state"] = f"0x{gs_ptr:X}" if gs_ptr else None
    if not gs_ptr:
        limits.append("game_state_chain_failed")

    status_ptr = None
    if pawn_ptr:
        status_ptr = _resolve_chain(mem, pawn_ptr, "player_status_component", offsets)
    state["pointers"]["status_component"] = f"0x{status_ptr:X}" if status_ptr else None
    if pawn_ptr and not status_ptr:
        limits.append("status_component_chain_failed")

    # Player position
    root_off = fields.get("root_component")
    loc_off = fields.get("relative_location")
    if pawn_ptr and root_off is not None and loc_off is not None:
        try:
            root = mem.read_ptr(pawn_ptr + _parse_off(root_off))
            loc = mem.read_vector3(root + _parse_off(loc_off))
            state["player"]["position"] = loc.as_dict()
        except MemoryReadError:
            limits.append("position_read_failed")

    if pawn_ptr:
        for key in ("mounted_dino", "carrying_dino"):
            ptr = _read_weak_ptr(mem, pawn_ptr, fields.get(key))
            state["player"][key] = _fmt_ptr(ptr)
        for key in ("dragging_character", "dragged_character"):
            ptr = _read_field_ptr(mem, pawn_ptr, fields.get(key))
            state["player"][key] = _fmt_ptr(ptr)
        inv = _read_field_ptr(mem, pawn_ptr, fields.get("my_inventory_component"))
        state["player"]["inventory_component"] = _fmt_ptr(inv)

        inventory_fields = offsets.get("inventory_fields") or {}
        if inventory_fields:
            equipment_snap, equipment_limits = _read_equipped_items(mem, inv, inventory_fields)
            if equipment_snap:
                state["equipment"] = equipment_snap
            limits.extend(equipment_limits)

        movement_snap, movement_limits = _read_movement_state(mem, pawn_ptr, fields)
        if movement_snap:
            state["movement"] = movement_snap
        limits.extend(movement_limits)

        flag_reads: dict[str, bool | None] = {}
        for flag_name, spec in (offsets.get("pawn_flags") or {}).items():
            if not isinstance(spec, dict):
                continue
            flag_reads[flag_name] = _read_bit_bool(
                mem, pawn_ptr, spec.get("offset"), int(spec.get("bit", 0))
            )
        if flag_reads:
            state["player"]["flags"] = flag_reads

        shoulder_snap, shoulder_limits = _read_shoulder_attach_snapshot(mem, pawn_ptr, fields)
        if shoulder_snap:
            state["shoulder"] = shoulder_snap
        limits.extend(shoulder_limits)

        dino_mount_snap, dino_mount_limits = _read_dino_mount_snapshot(mem, pawn_ptr, fields)
        if dino_mount_snap:
            state["dino_mount"] = dino_mount_snap
        limits.extend(dino_mount_limits)

        owl_snap, owl_limits = _read_owl_abilities_snapshot(
            mem, pawn_ptr, offsets, dino_mount=dino_mount_snap
        )
        if owl_snap:
            state["owl_abilities"] = owl_snap
        limits.extend(owl_limits)

    mission_paths = offsets.get("mission_paths") or {}
    if pc_ptr and mission_paths:
        mission_snap, mission_limits = _read_mission_state(mem, pc_ptr, mission_paths)
        if mission_snap:
            state["mission"] = mission_snap
        limits.extend(mission_limits)
    elif mission_paths:
        limits.append("mission_paths_unreadable")

    if pc_ptr:
        for key in ("has_view_only_inventory_open", "is_only_viewing_remote_inventory"):
            val = _read_bool_field(mem, pc_ptr, fields.get(key))
            if val is not None:
                state["controller"][key] = val
            elif fields.get(key) is not None:
                limits.append(f"controller_{key}_read_failed")

    if gs_ptr:
        float_keys = (
            "day_time",
            "night_time_speed_scale",
            "server_world_time_seconds_delta",
        )
        for key in float_keys:
            raw = _read_field_f32(mem, gs_ptr, fields.get(key))
            if raw is None:
                if fields.get(key) is not None:
                    limits.append(f"world_{key}_read_failed")
                continue
            val = _sanitize_world_float(key, raw)
            if val is None:
                limits.append(f"world_{key}_sanitized")
                continue
            state["world"][key] = val

        day_num_off = _parse_off(fields.get("day_number"))
        if day_num_off is not None:
            try:
                state["world"]["day_number"] = mem.read_u32(gs_ptr + day_num_off)
            except MemoryReadError:
                limits.append("world_day_number_read_failed")

    if status_ptr:
        for key, spec in (offsets.get("status_fields") or {}).items():
            if not isinstance(spec, dict):
                continue
            base_off = _parse_off(spec.get("offset"))
            idx = int(spec.get("index", 0))
            if base_off is None:
                continue
            try:
                state["status"][key] = mem.read_f32(status_ptr + base_off + idx * 4)
            except MemoryReadError:
                limits.append(f"status_{key}_read_failed")

        lvl_off = _parse_off(fields.get("character_level"))
        if lvl_off is not None:
            try:
                state["status"]["character_level"] = mem.read_u32(status_ptr + lvl_off)
            except MemoryReadError:
                limits.append("status_character_level_read_failed")

    return {"state": state, "limits": limits}


def build_digest(gate: GateResult, snapshot: dict, offsets: dict) -> dict:
    state = snapshot.get("state", {})
    digest_without_decode = {
        "schema": "ark_sp_memory_digest.v0.3",
        "updated_at": utc_now(),
        "policy": "singleplayer_read_only_no_battleye",
        "requirements": {
            "singleplayer_only": True,
            "battleye_disabled": gate.battleye_disabled,
            "no_api_calls": True,
            "no_player_identifiers": True,
        },
        "process": {"name": gate.process_name, "pid": gate.pid},
        "sp_gate": {
            "ok": gate.ok,
            "warnings": gate.warnings,
            "reasons": gate.reasons,
            "battleye_disabled": gate.battleye_disabled,
        },
        "offsets_build": offsets.get("build_label", "UNKNOWN_BUILD"),
        "offsets_schema": offsets.get("schema"),
        "state_snapshot": state,
        "limits": snapshot.get("limits", []),
    }
    decoded = decode_snapshot(digest_without_decode)
    digest_without_decode["decoded_state"] = decoded
    digest_without_decode["limits"] = list(
        dict.fromkeys(
            (digest_without_decode.get("limits") or [])
            + (decoded.get("limits") or [])
        )
    )
    return digest_without_decode


def write_outputs(digest: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DIGEST_FILE.write_text(json.dumps(digest, indent=2), encoding="utf-8")
    with STREAM_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(digest) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ASA singleplayer memory digest (read-only, BattlEye off)"
    )
    parser.add_argument("--offsets", type=Path, default=DEFAULT_OFFSETS)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()

    configure_output_dir(args.out_dir)
    offsets = load_offsets(args.offsets)

    while True:
        try:
            gate = verify_singleplayer(strict=True)
            mem = ASAMemoryProcess()
            snapshot = read_state_snapshot(mem, offsets)
            digest = build_digest(gate, snapshot, offsets)
            write_outputs(digest)
            pos = snapshot.get("state", {}).get("player", {}).get("position") or {}
            world = snapshot.get("state", {}).get("world", {})
            status = snapshot.get("state", {}).get("status", {})

            def _fmt_num(val: Any, prec: int = 1) -> str:
                return f"{val:.{prec}f}" if isinstance(val, (int, float)) else "?"

            decoded = digest.get("decoded_state") or {}
            session = decoded.get("session") or {}
            player_dec = decoded.get("player") or {}
            mission_dec = decoded.get("mission") or {}
            equipment_dec = decoded.get("equipment") or {}
            movement_dec = decoded.get("movement") or {}
            mission_label = mission_dec.get("mission_phase") or "idle"
            equip_count = equipment_dec.get("equipped_count", "?")
            movement_label = movement_dec.get("movement_mode") or "?"
            print(
                f"memory_digest ok pid={gate.pid} be_off={gate.battleye_disabled} "
                f"net={session.get('net_mode', '?')} "
                f"pos={_fmt_num(pos.get('x'))},{_fmt_num(pos.get('y'))},{_fmt_num(pos.get('z'))} "
                f"day={world.get('day_number', '?')} t={_fmt_num(world.get('day_time'), 3)} "
                f"hp={_fmt_num(status.get('health'))} "
                f"mounted={player_dec.get('mounted', False)} "
                f"glide={movement_dec.get('is_gliding', False)} "
                f"equip={equip_count} "
                f"mission={mission_label} "
                f"move={movement_label} "
                f"limits={','.join(snapshot.get('limits') or []) or 'none'}",
                flush=True,
            )
        except SingleplayerGateError as exc:
            print(f"SP GATE BLOCKED: {exc}", file=sys.stderr, flush=True)
            return 2
        except MemoryReadError as exc:
            print(f"memory read error: {exc}", file=sys.stderr, flush=True)
            if args.once:
                return 1
        except KeyboardInterrupt:
            print("stopped", flush=True)
            return 0

        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
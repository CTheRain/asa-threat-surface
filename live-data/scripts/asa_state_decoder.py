#!/usr/bin/env python3
"""Decode memory state snapshots using enum catalog (Phase C hooks for correlator)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CATALOG = SCRIPT_DIR.parent / "config" / "enum_catalog.json"

DECODER_SCHEMA = "ark_sp_state_decoded.v0.8"

SHOULDER_ATTACH_BASELINE = 5

CHIBI_LEVEL_MIN = 1
CHIBI_LEVEL_MAX = 500
# Chibi: cosmetic item skin (PrimalItemSkin_ChibiDino_*), not a creature.
CHIBI_EQUIPMENT_TYPES = frozenset({"Costume"})
# Shoulder creature: living tamed dino on shoulder (e.g. Gloon), not a chibi item.
# Gloon display name maps to LostCharge_LanternPet_Char_BP_C (lantern-pet shoulder mount).
SHOULDER_CREATURE_CLASS_REFS = frozenset(
    {
        "LostCharge_LanternPet_Char_BP_C",
        "LanternPet_Character_BP_C",
        "DinoCompanion_Character_BP_C",
    }
)
SHOULDER_CREATURE_EQUIPMENT_TYPES = frozenset({"Pet"})
SHOULDER_PET_EQUIPMENT_TYPES = SHOULDER_CREATURE_EQUIPMENT_TYPES  # alias


def _is_chibi_item(
    type_name: str | None,
    chibi_level: int | None,
    chibi_controller: str | None,
) -> bool:
    if type_name in CHIBI_EQUIPMENT_TYPES:
        return True
    return bool(
        chibi_controller
        and isinstance(chibi_level, int)
        and CHIBI_LEVEL_MIN <= chibi_level <= CHIBI_LEVEL_MAX
    )


def _is_active_chibi(slot: dict[str, Any]) -> bool:
    if not slot.get("is_chibi"):
        return False
    if slot.get("chibi_controller_ptr"):
        return True
    if slot.get("source") == "equipped_items":
        return bool(slot.get("is_equipped_flag"))
    return bool(slot.get("is_equipped_flag") and slot.get("equipment_type") in CHIBI_EQUIPMENT_TYPES)

ARMOR_EQUIPMENT_TYPES = frozenset({"Hat", "Shirt", "Pants", "Boots", "Gloves"})

STATUS_FIELD_TO_ENUM = {
    "health": "Health",
    "max_health": "Health",
    "stamina": "Stamina",
    "max_stamina": "Stamina",
    "torpidity": "Torpidity",
    "max_torpidity": "Torpidity",
    "oxygen": "Oxygen",
    "food": "Food",
    "water": "Water",
    "weight": "Weight",
}

VITAL_PAIRS = (
    ("health", "max_health", "health_pct"),
    ("stamina", "max_stamina", "stamina_pct"),
    ("torpidity", "max_torpidity", "torpidity_pct"),
)

WORLD_FLOAT_RULES: dict[str, dict[str, float | None]] = {
    "day_time": {"min": 0.0, "max": 86400.0 * 365.0},
    "night_time_speed_scale": {"min": 0.01, "max": 50.0},
    "server_world_time_seconds_delta": {"min": -1e9, "max": 1e9},
}


def load_catalog(path: Path = DEFAULT_CATALOG) -> dict:
    if not path.exists():
        return {"enums": {}, "reverse": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _enum_name(catalog: dict, enum_type: str, raw: int | str | None) -> str | None:
    if raw is None:
        return None
    rev = catalog.get("reverse", {}).get(enum_type, {})
    return rev.get(str(int(raw)))


def _pct(current: Any, maximum: Any) -> float | None:
    if not isinstance(current, (int, float)) or not isinstance(maximum, (int, float)):
        return None
    if maximum <= 0:
        return None
    return round(100.0 * current / maximum, 2)


def _day_phase(day_time: float | None) -> str | None:
    if day_time is None:
        return None
    if day_time < 0:
        return "unknown"
    hour = (day_time % 86400) / 3600.0
    if 5 <= hour < 8:
        return "dawn"
    if 8 <= hour < 18:
        return "day"
    if 18 <= hour < 21:
        return "dusk"
    return "night"


def _fmt_game_time(day_time: float | None) -> str | None:
    if day_time is None:
        return None
    secs = int(day_time % 86400)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _sanitize_world(world: dict) -> tuple[dict[str, Any], list[str]]:
    clean: dict[str, Any] = {}
    limits: list[str] = []
    for key, val in world.items():
        if not isinstance(val, (int, float)):
            clean[key] = val
            continue
        rule = WORLD_FLOAT_RULES.get(key)
        if not rule:
            clean[key] = val
            continue
        lo, hi = rule.get("min"), rule.get("max")
        if lo is not None and val < lo:
            limits.append(f"world_{key}_out_of_range")
            continue
        if hi is not None and val > hi:
            limits.append(f"world_{key}_out_of_range")
            continue
        clean[key] = val
    return clean, limits


def _decode_net_mode(
    session: dict,
    digest: dict,
    catalog: dict,
) -> tuple[str | None, int | None, str, list[str]]:
    limits: list[str] = []
    rev = catalog.get("reverse", {}).get("ENetModeBP", {})

    net_driver = session.get("net_driver")
    demo_net_driver = session.get("demo_net_driver")
    authority_game_mode = session.get("authority_game_mode")

    has_net_driver = bool(net_driver)
    has_demo = bool(demo_net_driver)
    has_authority = bool(authority_game_mode)

    if not has_net_driver and not has_demo:
        mode_id = 0
        source = "memory_uworld_no_net_driver"
        if digest.get("sp_gate", {}).get("ok"):
            source = "memory_uworld_no_net_driver+sp_gate"
        return rev.get("0", "Standalone"), mode_id, source, limits

    if has_net_driver and has_authority and not digest.get("sp_gate", {}).get("ok"):
        mode_id = 2
        return rev.get("2", "ListenServer"), mode_id, "memory_net_driver+authority_game_mode", limits

    if has_net_driver and not has_authority:
        mode_id = 3
        return rev.get("3", "Client"), mode_id, "memory_net_driver_no_authority", limits

    if has_net_driver:
        mode_id = 1
        limits.append("net_mode_heuristic_dedicated")
        return rev.get("1", "DedicatedServer"), mode_id, "memory_net_driver_heuristic", limits

    limits.append("net_mode_ambiguous")
    return None, None, "memory_inconclusive", limits


DINO_SADDLE_EQUIPMENT_TYPE = "DinoSaddle"
KNOWN_DINO_MOUNT_CLASS_REFS = frozenset({"Owl_Character_BP_C"})


def decode_dino_mount_state(
    dino_mount: dict[str, Any] | None,
    *,
    movement_mode: str | None = None,
    equipped_slots: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Detect saddle dino control — ASA swaps AcknowledgedPawn to the ridden dino."""
    if not dino_mount:
        return {
            "is_controlling_saddled_dino": False,
            "pawn_control_mode": "unknown",
            "has_rider": False,
            "limits": ["dino_mount_snapshot_missing"],
        }

    limits: list[str] = []
    has_rider = bool(dino_mount.get("has_rider"))
    has_saddle = any(
        s.get("equipment_type") == DINO_SADDLE_EQUIPMENT_TYPE for s in (equipped_slots or [])
    )
    controlling = has_rider or (has_saddle and movement_mode in ("MOVE_Flying", "MOVE_Walking"))
    if has_saddle and not has_rider:
        limits.append("dino_saddle_without_rider_weak")

    return {
        "is_controlling_saddled_dino": controlling,
        "pawn_control_mode": dino_mount.get("pawn_control_mode") or "unknown",
        "has_rider": has_rider,
        "rider_weak_index": dino_mount.get("rider_weak_index"),
        "rider_weak_serial": dino_mount.get("rider_weak_serial"),
        "rider_weak_index_hex": dino_mount.get("rider_weak_index_hex"),
        "has_dino_saddle_equipped": has_saddle,
        "movement_mode": movement_mode,
        "detection_source": "pawn_rider_weak+saddle+movement",
        "known_class_refs": sorted(KNOWN_DINO_MOUNT_CLASS_REFS),
        "limits": limits,
    }


def decode_owl_abilities_state(
    owl: dict[str, Any] | None,
    *,
    dino_mount: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Snow Owl freeze/encapsulate — EncapsulateIsActive @ Owl_Character_BP_C+0x2CE0."""
    if not owl or not owl.get("applicable"):
        return {
            "applicable": False,
            "is_encapsulated": False,
            "is_ice_crash_active": False,
            "freeze_state": "n/a",
            "limits": ["owl_abilities_not_applicable"],
        }

    limits: list[str] = []
    encapsulated = bool(owl.get("encapsulate_is_active"))
    ice_crash = bool(owl.get("ice_crash_is_active"))
    if owl.get("encapsulate_is_active") is None:
        limits.append("encapsulate_is_active_unreadable")
    if owl.get("ice_crash_is_active") is None:
        limits.append("ice_crash_is_active_unreadable")

    if encapsulated:
        freeze_state = "encapsulated"
    elif ice_crash:
        freeze_state = "ice_crash"
    else:
        freeze_state = "none"

    return {
        "applicable": True,
        "class_ref": owl.get("class_ref") or "Owl_Character_BP_C",
        "is_encapsulated": encapsulated,
        "is_ice_crash_active": ice_crash,
        "freeze_state": freeze_state,
        "encapsulate_is_active": owl.get("encapsulate_is_active"),
        "ice_crash_is_active": owl.get("ice_crash_is_active"),
        "detection_source": "owl_class_fields+has_rider",
        "limits": limits,
    }


def decode_shoulder_mount_state(
    shoulder: dict[str, Any] | None,
    *,
    dino_mount: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Infer lantern-pet shoulder mount state from attach graph + weak MountedDino index."""
    if dino_mount and dino_mount.get("has_rider"):
        return {
            "mount_state": "n/a_dino_pawn",
            "attach_animating": False,
            "has_lantern_pet_on_shoulder": False,
            "has_lantern_pet_grounded": False,
            "limits": ["shoulder_lantern_not_applicable_on_dino_pawn"],
        }

    if not shoulder:
        return {
            "mount_state": "unknown",
            "attach_animating": False,
            "has_lantern_pet_on_shoulder": False,
            "has_lantern_pet_grounded": False,
            "limits": ["shoulder_snapshot_missing"],
        }

    idx = shoulder.get("mounted_dino_weak_index")
    serial = shoulder.get("mounted_dino_weak_serial")
    count = shoulder.get("attach_child_count")
    baseline = shoulder.get("attach_baseline_count", SHOULDER_ATTACH_BASELINE)
    limits: list[str] = []

    if not isinstance(count, int):
        limits.append("attach_child_count_missing")
        count = 0

    attach_animating = count > baseline
    if attach_animating:
        mount_state = "transition"
    elif idx == 0:
        mount_state = "grounded"
    elif isinstance(idx, int) and idx > 0:
        mount_state = "mounted"
        limits.append("mounted_dino_weak_index_unresolved_gobject")
    else:
        mount_state = "unknown"
        limits.append("mounted_dino_weak_index_missing")

    return {
        "mount_state": mount_state,
        "attach_animating": attach_animating,
        "attach_child_count": count,
        "attach_baseline_count": baseline,
        "mounted_dino_weak_index": idx,
        "mounted_dino_weak_serial": serial,
        "mounted_dino_weak_index_hex": f"0x{idx:X}" if isinstance(idx, int) and idx > 0 else None,
        "attach_child_ptrs": shoulder.get("attach_child_ptrs") or [],
        "has_lantern_pet_on_shoulder": mount_state == "mounted",
        "has_lantern_pet_grounded": mount_state == "grounded",
        "detection_source": "attach_graph+mounted_dino_weak_index",
        "limits": limits,
    }


def _ptr_active(ptr: str | None) -> bool:
    if not ptr or ptr in ("0x0", "null"):
        return False
    try:
        val = int(ptr, 16) if isinstance(ptr, str) and ptr.startswith("0x") else int(ptr)
    except (TypeError, ValueError):
        return False
    if val & 7:
        return False
    if val in (0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF, 0x7FFFFFFFFFFFFFFF):
        return False
    if val >= 0x7FF000000000:
        return False
    return 0x10000 <= val <= 0x7FFFFFFFFFFF


def decode_snapshot(
    digest: dict | None,
    catalog: dict | None = None,
) -> dict[str, Any]:
    """Return decoded overlay for a memory digest row."""
    if not digest:
        return {
            "schema": DECODER_SCHEMA,
            "limits": ["no_memory_digest"],
        }

    catalog = catalog or load_catalog()
    snap = digest.get("state_snapshot") or {}
    session_raw = snap.get("session") or {}
    player = snap.get("player") or {}
    controller = snap.get("controller") or {}
    world_raw = snap.get("world") or {}
    status = snap.get("status") or {}
    flags = player.get("flags") or {}
    limits: list[str] = []

    world, world_limits = _sanitize_world(world_raw)
    limits.extend(world_limits)

    net_mode, net_mode_id, net_source, net_limits = _decode_net_mode(
        session_raw, digest, catalog
    )
    limits.extend(net_limits)
    if net_mode is None:
        limits.append("net_mode_unverified")

    rev = catalog.get("reverse", {})
    vitals_named: dict[str, Any] = {}
    for field, enum_member in STATUS_FIELD_TO_ENUM.items():
        if field not in status:
            continue
        vitals_named[field] = {
            "value": status[field],
            "status_slot": enum_member,
            "status_slot_enum": _enum_name(catalog, "EPrimalCharacterStatusValue", enum_member)
            if isinstance(enum_member, int)
            else enum_member,
        }

    vital_pcts: dict[str, float | None] = {}
    for cur_key, max_key, pct_key in VITAL_PAIRS:
        vital_pcts[pct_key] = _pct(status.get(cur_key), status.get(max_key))

    mounted_ptr = player.get("mounted_dino")
    mounted_flag = flags.get("is_mounted_flag")
    mission_raw = snap.get("mission") or {}
    mission_state_id = mission_raw.get("mission_state_raw")
    mission_state_name = _enum_name(catalog, "EMissionState", mission_state_id)
    has_active_mission = _ptr_active(mission_raw.get("active_mission"))
    raw_idx = mission_raw.get("active_mission_index")
    mission_index = None
    if isinstance(raw_idx, int):
        mission_index = -1 if raw_idx == 0xFFFFFFFF else raw_idx
    mission_block = {
        "has_active_mission": has_active_mission,
        "active_mission_ptr": mission_raw.get("active_mission"),
        "mission_data_buff_ptr": mission_raw.get("mission_data_buff"),
        "active_mission_hud_ptr": mission_raw.get("active_mission_hud"),
        "active_mission_index": mission_index,
        "current_missions_count": mission_raw.get("current_missions_count"),
        "mission_state_id": mission_state_id,
        "mission_state": mission_state_name,
        "mission_phase": mission_state_name or ("active" if has_active_mission else "idle"),
        "playing_mission_movie": mission_raw.get("playing_mission_movie"),
        "source": "hud_mission_data_buff",
    }

    equipment_raw = snap.get("equipment") or {}
    equipped_slots_pre: list[dict[str, Any]] = []
    for slot in equipment_raw.get("equipped_slots") or []:
        if isinstance(slot, dict):
            equipped_slots_pre.append(slot)

    movement_raw_pre = snap.get("movement") or {}
    movement_mode_id_pre = movement_raw_pre.get("movement_mode_raw")
    movement_mode_name_pre = _enum_name(catalog, "EMovementMode", movement_mode_id_pre)

    dino_mount_raw = snap.get("dino_mount") or {}
    dino_mount_block = decode_dino_mount_state(
        dino_mount_raw,
        movement_mode=movement_mode_name_pre,
        equipped_slots=equipped_slots_pre,
    )
    limits.extend(dino_mount_block.pop("limits", []))

    owl_raw = snap.get("owl_abilities") or {}
    owl_block = decode_owl_abilities_state(owl_raw, dino_mount=dino_mount_raw)
    limits.extend(owl_block.pop("limits", []))

    mounted = (
        _ptr_active(mounted_ptr)
        or bool(mounted_flag)
        or bool(dino_mount_block.get("is_controlling_saddled_dino"))
    )

    dragging_ptr = player.get("dragging_character")
    dragged_ptr = player.get("dragged_character")
    carrying_ptr = player.get("carrying_dino")

    interactions = {
        "mounted": mounted,
        "mounted_dino_ptr": mounted_ptr,
        "mounted_via_flag": bool(mounted_flag),
        "carrying_dino": _ptr_active(carrying_ptr),
        "carrying_dino_ptr": carrying_ptr,
        "dragging_character": _ptr_active(dragging_ptr),
        "dragging_character_ptr": dragging_ptr,
        "dragged_character": _ptr_active(dragged_ptr),
        "dragged_character_ptr": dragged_ptr,
        "is_dragging": bool(flags.get("is_dragging")),
        "is_local_dragging": bool(flags.get("is_local_dragging")),
        "is_being_dragged": bool(flags.get("is_being_dragged")),
        "is_dragging_grappling": bool(flags.get("is_dragging_grappling")),
        "is_sleeping": bool(flags.get("is_sleeping")),
        "is_prone": bool(flags.get("is_prone")),
        "has_inventory_component": _ptr_active(player.get("inventory_component")),
        "inventory_view_open": bool(controller.get("has_view_only_inventory_open")),
        "inventory_remote_view": bool(controller.get("is_only_viewing_remote_inventory")),
        "is_controlling_saddled_dino": dino_mount_block.get("is_controlling_saddled_dino"),
        "pawn_control_mode": dino_mount_block.get("pawn_control_mode"),
        "is_owl_encapsulated": owl_block.get("is_encapsulated"),
        "owl_freeze_state": owl_block.get("freeze_state"),
    }

    day_time = world.get("day_time") if isinstance(world.get("day_time"), (int, float)) else None

    def _decode_inventory_slot(
        slot: dict[str, Any],
        *,
        source: str,
    ) -> dict[str, Any]:
        type_id = slot.get("equipment_type_id")
        type_name = _enum_name(catalog, "EPrimalEquipmentType", type_id)
        chibi_level = slot.get("chibi_level")
        chibi_controller = slot.get("chibi_controller_ptr")
        is_chibi_item = _is_chibi_item(type_name, chibi_level, chibi_controller)
        is_shoulder_creature = type_name in SHOULDER_CREATURE_EQUIPMENT_TYPES
        return {
            "source": source,
            "index": slot.get("index"),
            "item_ptr": slot.get("item_ptr"),
            "equipment_type_id": type_id,
            "equipment_type": type_name,
            "equipment_type_enum": type_name,
            "is_equipped_flag": slot.get("is_equipped_flag"),
            "chibi_level": chibi_level,
            "chibi_controller_ptr": chibi_controller,
            "is_chibi": is_chibi_item,
            "is_shoulder_creature": is_shoulder_creature,
            "is_shoulder_pet": is_shoulder_creature,
        }

    equipped_slots: list[dict[str, Any]] = []
    item_slots: list[dict[str, Any]] = []
    armor_types: list[str] = []
    for slot in equipment_raw.get("equipped_slots") or []:
        if not isinstance(slot, dict):
            continue
        entry = _decode_inventory_slot(slot, source="equipped_items")
        equipped_slots.append(entry)
        if entry.get("equipment_type") in ARMOR_EQUIPMENT_TYPES:
            armor_types.append(entry["equipment_type"])

    for slot in equipment_raw.get("item_slots") or []:
        if not isinstance(slot, dict):
            continue
        item_slots.append(_decode_inventory_slot(slot, source="item_slots"))

    all_slots = (*equipped_slots, *item_slots)
    chibi_slots = [
        {
            "source": s.get("source"),
            "index": s.get("index"),
            "equipment_type": s.get("equipment_type"),
            "chibi_level": s.get("chibi_level"),
            "chibi_controller_ptr": s.get("chibi_controller_ptr"),
            "is_active": _is_active_chibi(s),
        }
        for s in all_slots
        if s.get("is_chibi")
    ]
    has_chibi = any(s.get("is_active") for s in chibi_slots)
    has_shoulder_creature = any(s.get("is_shoulder_creature") for s in equipped_slots)
    shoulder_raw = snap.get("shoulder") or {}
    shoulder_block = decode_shoulder_mount_state(shoulder_raw, dino_mount=dino_mount_raw)
    limits.extend(shoulder_block.pop("limits", []))

    equipment_block = {
        "inventory_component_ptr": equipment_raw.get("inventory_component"),
        "inventory_item_count": equipment_raw.get("inventory_item_count"),
        "equipped_count": equipment_raw.get("equipped_count"),
        "equipped_slots": equipped_slots,
        "item_slot_count": equipment_raw.get("item_slot_count"),
        "item_slots": item_slots,
        "armor_piece_count": len(armor_types),
        "armor_slots": sorted(set(armor_types)),
        "has_weapon": any(s.get("equipment_type") == "Weapon" for s in equipped_slots),
        "has_shield": any(s.get("equipment_type") == "Shield" for s in equipped_slots),
        "has_chibi_equipped": has_chibi,
        "has_shoulder_creature_equipped": has_shoulder_creature,
        "has_shoulder_pet_equipped": has_shoulder_creature,
        "has_shoulder_lantern_pet_mounted": shoulder_block.get("has_lantern_pet_on_shoulder"),
        "has_shoulder_lantern_pet_grounded": shoulder_block.get("has_lantern_pet_grounded"),
        "chibi_slots": chibi_slots,
        "taxonomy": {
            "chibi": "cosmetic_item_skin_not_creature",
            "shoulder_creature": "living_tamed_dino_actor",
            "known_shoulder_creature_class_refs": sorted(SHOULDER_CREATURE_CLASS_REFS),
            "gloon": {
                "display_name": "Gloon",
                "class_ref": "LostCharge_LanternPet_Char_BP_C",
                "mount_path": "spawned_actor_BPCanMountOnCharacter",
            },
        },
    }

    movement_raw = snap.get("movement") or {}
    movement_mode_id = movement_raw.get("movement_mode_raw")
    movement_mode_name = _enum_name(catalog, "EMovementMode", movement_mode_id)
    is_falling = movement_mode_id == 3 or movement_mode_name == "MOVE_Falling"
    is_flying = movement_mode_id == 5 or movement_mode_name == "MOVE_Flying"
    has_accessory = any(s.get("equipment_type") == "Accessory0" for s in equipped_slots)
    movement_block = {
        "character_movement_ptr": movement_raw.get("character_movement_ptr"),
        "movement_mode_id": movement_mode_id,
        "movement_mode": movement_mode_name,
        "movement_mode_enum": movement_mode_name,
        "custom_movement_mode": movement_raw.get("custom_movement_mode"),
        "is_flying": is_flying,
        "is_falling": is_falling,
        "is_swimming": movement_mode_id == 4 or movement_mode_name == "MOVE_Swimming",
        "is_gliding": is_falling and has_accessory and not mounted,
        "is_parachuting": is_flying and has_accessory and not mounted,
        "has_shoulder_creature_equipped": has_shoulder_creature,
        "has_shoulder_pet_equipped": has_shoulder_creature,
        "has_shoulder_lantern_pet_mounted": shoulder_block.get("has_lantern_pet_on_shoulder"),
        "has_shoulder_lantern_pet_grounded": shoulder_block.get("has_lantern_pet_grounded"),
        "has_chibi_equipped": has_chibi,
    }

    return {
        "schema": DECODER_SCHEMA,
        "catalog_schema": catalog.get("schema"),
        "session": {
            "net_mode": net_mode,
            "net_mode_id": net_mode_id,
            "net_mode_enum": _enum_name(catalog, "ENetModeBP", net_mode_id),
            "net_mode_source": net_source,
            "net_driver_ptr": session_raw.get("net_driver"),
            "demo_net_driver_ptr": session_raw.get("demo_net_driver"),
            "authority_game_mode_ptr": session_raw.get("authority_game_mode"),
        },
        "player": interactions,
        "dino_mount": dino_mount_block,
        "owl_abilities": owl_block,
        "shoulder": shoulder_block,
        "equipment": equipment_block,
        "movement": movement_block,
        "mission": mission_block,
        "world": {
            "day_number": world.get("day_number"),
            "day_time": day_time,
            "day_time_hms": _fmt_game_time(day_time),
            "day_phase": _day_phase(day_time),
            "server_world_time_seconds_delta": world.get("server_world_time_seconds_delta"),
            "night_time_speed_scale": world.get("night_time_speed_scale"),
            "dropped_fields": sorted(set(world_raw) - set(world)),
        },
        "status": {
            "vitals_named": vitals_named,
            "health_pct": vital_pcts.get("health_pct"),
            "stamina_pct": vital_pcts.get("stamina_pct"),
            "torpidity_pct": vital_pcts.get("torpidity_pct"),
            "character_level": status.get("character_level"),
        },
        "limits": limits,
    }
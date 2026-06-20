#!/usr/bin/env python3
"""Convert Dumper-7 Dumpspace JSON output into memory_offsets.json for asa_memory_reader.

Reads OffsetsInfo.json + ClassesInfo.json from a Dumper-7 dump folder and emits
curated pointer chains / field offsets for live state probing (not vitals-only).

Usage:
  python asa_dumper7_to_offsets.py --dump-dir live-data/dumps/sdk/<GameVersion-GameName>/Dumpspace
  python asa_dumper7_to_offsets.py --auto  # newest dump under live-data/dumps/sdk
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_LIVE_DATA = SCRIPT_DIR.parent
DEFAULT_DUMPS_ROOT = DEFAULT_LIVE_DATA / "dumps" / "sdk"
DEFAULT_OUT = DEFAULT_LIVE_DATA / "config" / "memory_offsets.json"

# Pointer-hop chain from GWorld to local pawn (UE / ASA layout).
# Each entry is a member name on the current object; last hop may be final field.
CHAIN_LOCAL_PLAYER_PAWN = [
    "OwningGameInstance",
    "LocalPlayers",
    "PlayerController",
    "AcknowledgedPawn",  # fallback: Pawn
]

# Named state fields to export when found on resolved classes.
FIELD_CANDIDATES: dict[str, list[tuple[str, str, str]]] = {
    "pawn": [
        ("root_component", "RootComponent", "AActor"),
        ("relative_location", "RelativeLocation", "USceneComponent"),
        ("mounted_dino", "MountedDino", "APrimalCharacter"),
        ("carrying_dino", "CarryingDino", "APrimalCharacter"),
        ("dragging_character", "DraggingCharacter", "APrimalCharacter"),
        ("dragged_character", "DraggedCharacter", "APrimalCharacter"),
        ("my_inventory_component", "MyInventoryComponent", "APrimalCharacter"),
    ],
    "world": [
        ("game_state", "GameState", "UWorld"),
        ("net_driver", "NetDriver", "UWorld"),
        ("demo_net_driver", "DemoNetDriver", "UWorld"),
        ("authority_game_mode", "AuthorityGameMode", "UWorld"),
    ],
    "player_controller": [
        ("my_hud", "MyHUD", "APlayerController"),
        ("has_view_only_inventory_open", "bHasViewOnlyInventoryOpen", "AShooterPlayerController"),
        (
            "is_only_viewing_remote_inventory",
            "bIsOnlyViewingRemoteInventory",
            "AShooterPlayerController",
        ),
    ],
    "shooter_hud": [
        ("active_mission_hud", "MyPlayerActiveMissionHUD", "AShooterHUD"),
    ],
    "hud_active_mission_widget": [
        ("widget_active_mission", "ActiveMission", "UHUDActiveMissionWidget"),
        ("widget_mission_data", "MissionData", "UHUDActiveMissionWidget"),
    ],
    "mission_data_buff": [
        ("md_active_mission", "ActiveMission", "APrimalBuff_MissionData"),
        ("md_active_mission_index", "ActiveMissionIndex", "APrimalBuff_MissionData"),
        ("md_current_missions", "CurrentMissions", "APrimalBuff_MissionData"),
        ("md_playing_mission_movie", "bIsPlayingMissionMovie", "APrimalBuff_MissionData"),
    ],
    "mission_type": [
        ("mt_mission_state", "MissionState", "AMissionType"),
    ],
    "game_state": [
        ("server_world_time_seconds_delta", "ServerWorldTimeSecondsDelta", "AGameStateBase"),
    ],
    "shooter_game_state": [
        ("day_number", "DayNumber", "AShooterGameState"),
        ("day_time", "DayTime", "AShooterGameState"),
        ("night_time_speed_scale", "NightTimeSpeedScale", "AShooterGameState"),
    ],
    "status_scalar": [
        ("character_level", "BaseCharacterLevel", "UPrimalCharacterStatusComponent"),
    ],
}

# TArray-like status slots: EPrimalCharacterStatusValue indices
STATUS_ARRAY_FIELDS: dict[str, tuple[str, int]] = {
    "health": ("CurrentStatusValues", 0),
    "max_health": ("MaxStatusValues", 0),
    "stamina": ("CurrentStatusValues", 1),
    "torpidity": ("CurrentStatusValues", 2),
    "oxygen": ("CurrentStatusValues", 3),
    "food": ("CurrentStatusValues", 4),
    "water": ("CurrentStatusValues", 5),
    "weight": ("CurrentStatusValues", 7),
}

CHAIN_SPECS: dict[str, list[tuple[str, list[str], str]]] = {
    "local_player_controller": [
        ("UWorld", ["UWorld"], "OwningGameInstance"),
        ("UGameInstance", ["UGameInstance", "UShooterGameInstance"], "LocalPlayers"),
        ("ULocalPlayer", ["ULocalPlayer", "UPlayer"], "PlayerController"),
    ],
    "local_player_pawn": [
        ("UWorld", ["UWorld"], "OwningGameInstance"),
        ("UGameInstance", ["UGameInstance", "UShooterGameInstance"], "LocalPlayers"),
        ("ULocalPlayer", ["ULocalPlayer", "UPlayer"], "PlayerController"),
        ("APlayerController", ["APlayerController", "AShooterPlayerController"], "AcknowledgedPawn"),
    ],
    "game_state": [
        ("UWorld", ["UWorld"], "GameState"),
    ],
    "player_status_component": [
        ("APrimalCharacter", ["APrimalCharacter", "AShooterCharacter", "APawn"], "MyCharacterStatusComponent"),
    ],
}

CLASS_ALIASES: dict[str, list[str]] = {
    "AActor": ["AActor"],
    "APawn": ["APawn", "AShooterCharacter", "APrimalCharacter"],
    "APrimalCharacter": ["APrimalCharacter", "AShooterCharacter"],
    "AShooterCharacter": ["AShooterCharacter", "APrimalCharacter"],
    "APlayerController": ["APlayerController", "AShooterPlayerController"],
    "AShooterPlayerController": ["AShooterPlayerController", "APlayerController"],
    "ULocalPlayer": ["ULocalPlayer", "UPlayer"],
    "UGameInstance": ["UGameInstance", "UShooterGameInstance"],
    "UWorld": ["UWorld"],
    "USceneComponent": ["USceneComponent", "UPrimitiveComponent"],
    "AGameStateBase": ["AGameStateBase"],
    "AGameState": ["AGameState"],
    "AShooterGameState": ["AShooterGameState", "AShooterGameState_C"],
    "UPrimalCharacterStatusComponent": [
        "UPrimalCharacterStatusComponent",
        "UPrimalCharacterStatusComponent_C",
    ],
    "AShooterHUD": ["AShooterHUD", "AHUD"],
    "AHUD": ["AHUD"],
    "UHUDActiveMissionWidget": ["UHUDActiveMissionWidget"],
    "APrimalBuff_MissionData": ["APrimalBuff_MissionData"],
    "AMissionType": ["AMissionType"],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def hex_offset(value: int | str) -> str:
    if isinstance(value, str):
        value = value.strip()
        if value.lower().startswith("0x"):
            return f"0x{int(value, 16):X}"
        return f"0x{int(value):X}"
    return f"0x{int(value):X}"


def parse_classes_info(classes_info: dict) -> dict[str, dict[str, int]]:
    """Build class_name -> {member_name: offset}."""
    classes: dict[str, dict[str, int]] = {}
    entries = classes_info.get("data", classes_info)
    if not isinstance(entries, list):
        return classes

    for item in entries:
        if not isinstance(item, dict):
            continue
        for class_name, members in item.items():
            member_map: dict[str, int] = {}
            if not isinstance(members, list):
                continue
            for member_entry in members:
                if not isinstance(member_entry, dict):
                    continue
                for member_name, payload in member_entry.items():
                    if member_name.startswith("__"):
                        continue
                    if not isinstance(payload, (list, tuple)) or len(payload) < 2:
                        continue
                    offset = payload[1]
                    if isinstance(offset, int):
                        member_map[member_name] = offset
            classes[class_name] = member_map
    return classes


def parse_offsets_info(offsets_info: dict) -> dict[str, int]:
    """Extract OFFSET_* values from OffsetsInfo.json."""
    out: dict[str, int] = {}
    data = offsets_info.get("data", offsets_info)
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, int):
                out[key] = value
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for key, value in item.items():
                    if isinstance(value, int):
                        out[key] = value
    return out


def find_class(classes: dict[str, dict[str, int]], aliases: list[str]) -> tuple[str, dict[str, int]] | None:
    for name in aliases:
        if name in classes:
            return name, classes[name]
    # Fuzzy: strip _C suffix
    for name in aliases:
        for key in classes:
            if key.rstrip("_C") == name.rstrip("_C"):
                return key, classes[key]
    return None


def member_offset(
    classes: dict[str, dict[str, int]],
    class_aliases: list[str],
    member: str,
) -> tuple[str, int] | None:
    for alias in class_aliases:
        members = classes.get(alias)
        if not members:
            continue
        if member in members:
            return alias, members[member]
        for k, v in members.items():
            if k.lower() == member.lower():
                return alias, v
    return None


def build_chain(
    classes: dict[str, dict[str, int]],
    spec_name: str,
) -> tuple[list[str], list[str], dict[str, int]]:
    """Return (offsets, limits, tarray_at)."""
    chain: list[str] = []
    limits: list[str] = []
    tarray_at: dict[str, int] = {}
    steps = CHAIN_SPECS.get(spec_name, [])

    for hop, (label, aliases, member) in enumerate(steps):
        hit = member_offset(classes, aliases, member)
        if not hit:
            if member == "AcknowledgedPawn":
                hit = member_offset(classes, aliases, "Pawn")
            if not hit:
                limits.append(f"chain_missing:{spec_name}:{label}.{member}")
                break
        _class_name, off = hit
        chain.append(hex_offset(off))
        if member == "LocalPlayers":
            tarray_at[str(hop)] = 0
            limits.append("local_players_is_tarray:index_0")

    if not chain:
        limits.append(f"{spec_name}_chain_empty")
    return chain, limits, tarray_at


def build_pawn_chain(classes: dict[str, dict[str, int]]) -> tuple[list[str], list[str]]:
    chain, limits, _ = build_chain(classes, "local_player_pawn")
    return chain, limits


def collect_mission_paths(classes: dict[str, dict[str, int]]) -> dict[str, str | None]:
    """Flat hop offsets for controller -> HUD -> mission buff -> mission type."""
    paths: dict[str, str | None] = {}
    for _group, candidates in FIELD_CANDIDATES.items():
        if _group not in {
            "player_controller",
            "shooter_hud",
            "hud_active_mission_widget",
            "mission_data_buff",
            "mission_type",
        }:
            continue
        for field_key, member, class_hint in candidates:
            aliases = CLASS_ALIASES.get(class_hint, [class_hint])
            hit = member_offset(classes, aliases, member)
            paths[field_key] = hex_offset(hit[1]) if hit else None
    return paths


def collect_fields(classes: dict[str, dict[str, int]]) -> tuple[dict[str, str | None], list[str]]:
    fields: dict[str, str | None] = {}
    limits: list[str] = []

    for _group, candidates in FIELD_CANDIDATES.items():
        for field_key, member, class_hint in candidates:
            if field_key in fields and fields[field_key] is not None:
                continue
            aliases = CLASS_ALIASES.get(class_hint, [class_hint])
            hit = member_offset(classes, aliases, member)
            if hit:
                _cls, off = hit
                fields[field_key] = hex_offset(off)
            else:
                if field_key not in fields:
                    fields[field_key] = None

    missing = [k for k, v in fields.items() if v is None]
    if missing:
        limits.append(f"fields_not_found:{','.join(missing[:12])}")
    return fields, limits


def collect_status_fields(
    classes: dict[str, dict[str, int]],
) -> tuple[dict[str, dict], list[str]]:
    """Status array slots on UPrimalCharacterStatusComponent."""
    out: dict[str, dict] = {}
    limits: list[str] = []
    aliases = CLASS_ALIASES["UPrimalCharacterStatusComponent"]

    for field_key, (member, index) in STATUS_ARRAY_FIELDS.items():
        hit = member_offset(classes, aliases, member)
        if hit:
            _cls, base_off = hit
            out[field_key] = {
                "base": "player_status_component",
                "offset": hex_offset(base_off),
                "index": index,
                "element_size": 4,
                "type": "f32",
            }
        else:
            limits.append(f"status_missing:{field_key}")

    return out, limits


def find_latest_dumpspace(root: Path) -> Path | None:
    if not root.exists():
        return None
    candidates = list(root.glob("*/Dumpspace/OffsetsInfo.json"))
    if not candidates:
        candidates = list(root.glob("**/Dumpspace/OffsetsInfo.json"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime).parent


def find_latest_cppsdk(root: Path) -> Path | None:
    """Newest version folder that has CppSDK/SDK/Basic.hpp (Dumpspace may be missing after crash)."""
    if not root.exists():
        return None
    candidates = [
        p.parent.parent.parent  # .../<version>/CppSDK/SDK/Basic.hpp
        for p in root.glob("*/CppSDK/SDK/Basic.hpp")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


_MEMBER_RE = re.compile(
    r"^\s+[\w:<>,\s\*&\[\]]+\s+(\w+)(?:\[[^\]]*\])?\s*;\s*//\s*(0x[0-9A-Fa-f]+)",
    re.MULTILINE,
)
_BASIC_OFFSET_RE = re.compile(
    r"^\s*constexpr\s+int32\s+(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+);",
    re.MULTILINE,
)


def _extract_class_body(text: str, class_name: str) -> str | None:
    match = re.search(
        rf"\bclass\s+(?:alignas\([^)]+\)\s+)?{re.escape(class_name)}(?:\s+final)?\s*(?::|\{{)",
        text,
    )
    if not match:
        return None
    idx = match.start()
    brace = text.find("{", idx)
    if brace < 0:
        return None
    depth = 0
    for i in range(brace, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace : i + 1]
    return None


def parse_cppsdk_members(sdk_files: list[Path], class_name: str) -> dict[str, int]:
    members: dict[str, int] = {}
    for path in sdk_files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        body = _extract_class_body(text, class_name)
        if not body:
            continue
        for match in _MEMBER_RE.finditer(body):
            name, off = match.group(1), int(match.group(2), 16)
            members.setdefault(name, off)
    return members


def parse_basic_static_offsets(basic_hpp: Path) -> dict[str, int]:
    if not basic_hpp.exists():
        return {}
    text = basic_hpp.read_text(encoding="utf-8", errors="replace")
    start = text.find("namespace Offsets")
    if start < 0:
        return {}
    end = text.find("namespace InSDKUtils", start)
    block = text[start:end] if end > start else text[start:]
    out: dict[str, int] = {}
    for match in _BASIC_OFFSET_RE.finditer(block):
        name, raw = match.group(1), match.group(2)
        out[name] = int(raw, 16) if raw.lower().startswith("0x") else int(raw)
    return out


def _chain_entry(
    chain: list[str], tarray_at: dict[str, int] | None = None
) -> dict | list[str]:
    if tarray_at:
        return {"offsets": chain, "tarray_at": {str(k): v for k, v in tarray_at.items()}}
    return chain


def _pawn_flag_catalog() -> dict[str, dict]:
    """APrimalCharacter bitfields for interaction decode (Phase C)."""
    return {
        "is_sleeping": {"offset": "0x16C8", "bit": 0},
        "is_local_dragging": {"offset": "0x16C8", "bit": 3},
        "is_being_dragged": {"offset": "0x16C8", "bit": 4},
        "is_dragging": {"offset": "0x16C8", "bit": 6},
        "is_dragging_grappling": {"offset": "0x16C8", "bit": 7},
        "is_mounted_flag": {"offset": "0x16CE", "bit": 5},
        "is_prone": {"offset": "0x16C7", "bit": 1},
    }


def _state_keys_catalog() -> dict:
    return {
        "session.net_mode": {
            "enum_type": "ENetModeBP",
            "fields": ["net_driver", "demo_net_driver", "authority_game_mode"],
            "chain": "gworld",
        },
        "player.pawn.position": {
            "requires": ["root_component", "relative_location"],
            "chain": "local_player_pawn",
        },
        "player.pawn.mounted_dino": {"field": "mounted_dino", "chain": "local_player_pawn"},
        "player.pawn.interactions": {
            "chain": "local_player_pawn",
            "fields": [
                "mounted_dino",
                "carrying_dino",
                "dragging_character",
                "dragged_character",
            ],
            "flags": list(_pawn_flag_catalog().keys()),
        },
        "player.controller.inventory_ui": {
            "chain": "local_player_controller",
            "fields": ["has_view_only_inventory_open", "is_only_viewing_remote_inventory"],
        },
        "player.mission": {
            "chain": "local_player_controller",
            "path": [
                "my_hud",
                "active_mission_hud",
                "widget_mission_data",
                "md_active_mission",
                "mt_mission_state",
            ],
            "enum": "EMissionState",
        },
        "player.status.vitals": {"base": "player_status_component", "from": "status_fields"},
        "world.game_state.time": {
            "chain": "game_state",
            "fields": ["day_time", "day_number", "server_world_time_seconds_delta"],
        },
    }


def assemble_offsets_document(
    *,
    classes: dict[str, dict[str, int]],
    gworld: int | None,
    build_label: str,
    source: dict,
    extra_limits: list[str] | None = None,
    notes: list[str] | None = None,
) -> dict:
    pc_chain, pc_limits, pc_tarray = build_chain(classes, "local_player_controller")
    pawn_chain, pawn_limits, pawn_tarray = build_chain(classes, "local_player_pawn")
    gs_chain, gs_limits, gs_tarray = build_chain(classes, "game_state")
    st_chain, st_limits, st_tarray = build_chain(classes, "player_status_component")
    fields, field_limits = collect_fields(classes)
    mission_paths = collect_mission_paths(classes)
    status_fields, status_limits = collect_status_fields(classes)
    pawn_flags = _pawn_flag_catalog()

    limits = pc_limits + pawn_limits + gs_limits + st_limits + field_limits + status_limits
    missing_mission = [k for k, v in mission_paths.items() if v is None]
    if missing_mission:
        limits.append(f"mission_paths_missing:{','.join(missing_mission[:8])}")
    if extra_limits:
        limits.extend(extra_limits)
    if not gworld:
        limits.append("gworld_missing")

    return {
        "schema": "ark_sp_memory_offsets.v0.5",
        "game": "ARK: Survival Ascended",
        "platform": "Windows",
        "process": "ArkAscended.exe",
        "generated_at": utc_now(),
        "source": source,
        "build_label": build_label,
        "GWorld": hex_offset(gworld) if gworld else None,
        "chains": {
            "local_player_controller": _chain_entry(pc_chain, pc_tarray or None),
            "local_player_pawn": _chain_entry(pawn_chain, pawn_tarray or None),
            "game_state": _chain_entry(gs_chain, gs_tarray or None),
            "player_status_component": _chain_entry(st_chain, st_tarray or None),
        },
        "fields": fields,
        "mission_paths": mission_paths,
        "pawn_flags": pawn_flags,
        "status_fields": status_fields,
        "state_keys": _state_keys_catalog(),
        "limits": limits,
        "notes": notes
        or [
            "Re-run Dumper-7 + export after every ASA patch.",
            "FVector reads use UE5 double precision (24 bytes).",
        ],
    }


def build_offsets_from_cppsdk(version_dir: Path) -> dict:
    sdk_dir = version_dir / "CppSDK" / "SDK"
    basic_hpp = sdk_dir / "Basic.hpp"
    sdk_files = [
        sdk_dir / "Engine_classes.hpp",
        sdk_dir / "ShooterGame_classes.hpp",
    ]

    static = parse_basic_static_offsets(basic_hpp)
    classes: dict[str, dict[str, int]] = {}
    for class_name in {
        "UWorld",
        "UGameInstance",
        "UShooterGameInstance",
        "ULocalPlayer",
        "UPlayer",
        "APlayerController",
        "AShooterPlayerController",
        "AShooterHUD",
        "AHUD",
        "UHUDActiveMissionWidget",
        "APrimalBuff_MissionData",
        "AMissionType",
        "AActor",
        "USceneComponent",
        "AGameStateBase",
        "AGameState",
        "AShooterGameState",
        "UPrimalCharacterStatusComponent",
        "APrimalCharacter",
        "AShooterCharacter",
    }:
        parsed = parse_cppsdk_members(sdk_files, class_name)
        if parsed:
            classes[class_name] = parsed

    gworld = static.get("GWorld")
    build_label = version_dir.name
    m = re.match(r"([\d.]+)-(.+)", build_label)
    if m:
        build_label = f"ASA_{m.group(1)}_{m.group(2).replace(' ', '_')}"

    doc = assemble_offsets_document(
        classes=classes,
        gworld=gworld,
        build_label=build_label,
        source={
            "dumper": "Dumper-7",
            "dump_dir": str(version_dir),
            "format": "CppSDK",
            "basic_hpp": str(basic_hpp),
            "sdk_files": [str(p) for p in sdk_files if p.exists()],
        },
        extra_limits=["source_cppsdk_fallback"],
        notes=[
            "Generated from Dumper-7 CppSDK fallback.",
            "Run asa_cppsdk_to_dumpspace.py for Dumpspace-compatible JSON from same tree.",
        ],
    )
    doc["static_offsets"] = {k.lower(): hex_offset(v) for k, v in static.items()}
    return doc


def build_offsets(dump_dir: Path) -> dict:
    offsets_path = dump_dir / "OffsetsInfo.json"
    classes_path = dump_dir / "ClassesInfo.json"
    if not offsets_path.exists():
        raise FileNotFoundError(f"Missing {offsets_path}")
    if not classes_path.exists():
        raise FileNotFoundError(f"Missing {classes_path}")

    offsets_raw = load_json(offsets_path)
    classes_raw = load_json(classes_path)
    static_offsets = parse_offsets_info(offsets_raw)
    classes = parse_classes_info(classes_raw)

    gworld = static_offsets.get("OFFSET_GWORLD")
    build_label = dump_dir.parent.name
    m = re.match(r"([\d.]+)-(.+)", build_label)
    if m:
        build_label = f"ASA_{m.group(1)}_{m.group(2).replace(' ', '_')}"

    doc = assemble_offsets_document(
        classes=classes,
        gworld=gworld,
        build_label=build_label,
        source={
            "dumper": "Dumper-7",
            "dump_dir": str(dump_dir),
            "format": "Dumpspace",
            "offsets_info": str(offsets_path),
            "classes_info": str(classes_path),
        },
        notes=["Generated from Dumper-7 Dumpspace JSON."],
    )
    doc["static_offsets"] = {
        k.lower().replace("offset_", ""): hex_offset(v)
        for k, v in static_offsets.items()
        if k.startswith("OFFSET_") or k.startswith("INDEX_")
    }
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert Dumper-7 dump to memory_offsets.json")
    parser.add_argument("--dump-dir", type=Path, help="Path to .../Dumpspace folder")
    parser.add_argument(
        "--auto",
        action="store_true",
        help=f"Use newest dump under {DEFAULT_DUMPS_ROOT}",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if args.auto:
        dump_dir = find_latest_dumpspace(DEFAULT_DUMPS_ROOT)
        if dump_dir:
            result = build_offsets(dump_dir)
        else:
            version_dir = find_latest_cppsdk(DEFAULT_DUMPS_ROOT)
            if not version_dir:
                print(f"No Dumpspace or CppSDK dump found under {DEFAULT_DUMPS_ROOT}")
                return 1
            print(f"Dumpspace missing — using CppSDK fallback: {version_dir.name}")
            result = build_offsets_from_cppsdk(version_dir)
    elif args.dump_dir:
        dump_dir = args.dump_dir
        if (dump_dir / "CppSDK" / "SDK" / "Basic.hpp").exists():
            result = build_offsets_from_cppsdk(dump_dir)
        elif dump_dir.name != "Dumpspace":
            candidate = dump_dir / "Dumpspace"
            if candidate.exists():
                dump_dir = candidate
            result = build_offsets(dump_dir)
        else:
            result = build_offsets(dump_dir)
    else:
        parser.error("Provide --dump-dir or --auto")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(f"wrote {args.out}")
    print(f"build_label={result['build_label']}")
    print(f"GWorld={result.get('GWorld')}")
    print(f"chain_hops={len(result['chains']['local_player_pawn'])}")
    found_fields = sum(1 for v in result["fields"].values() if v)
    print(f"fields_found={found_fields}/{len(result['fields'])}")
    if result["limits"]:
        print(f"limits={'; '.join(result['limits'][:6])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
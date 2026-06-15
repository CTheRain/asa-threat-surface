#!/usr/bin/env python3
"""Read-only ARK: Survival Ascended memory digest — SINGLEPLAYER ONLY.

Writes memory_digest.json and appends memory_stream.jsonl under ARK_LIVE_DATA.
Does not write game memory. Refuses dedicated/multiplayer sessions and BattlEye-on play.

Requirements:
  - Singleplayer session only (local SavedArksLocal)
  - BattlEye disabled (-NoBattlEye launch flag)
  - No API calls, tokens, or player-identifying strings in output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from asa_memory_process import ASAMemoryProcess, MemoryReadError
from asa_sp_gate import GateResult, SingleplayerGateError, verify_singleplayer

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


def read_player_slice(mem: ASAMemoryProcess, offsets: dict) -> dict:
    limits: list[str] = []
    out: dict = {
        "gworld_ptr": None,
        "pawn_ptr": None,
        "position": None,
        "vitals": {},
    }

    gworld_ptr = mem.resolve_gworld(offsets)
    out["gworld_ptr"] = f"0x{gworld_ptr:X}" if gworld_ptr else None
    if not gworld_ptr:
        limits.append("gworld_offset_missing")
        return out | {"limits": limits}

    chain = offsets.get("chains", {}).get("local_player_pawn") or []
    if not chain:
        limits.append("local_player_pawn_chain_missing")
        return out | {"limits": limits}

    try:
        pawn_ptr = mem.follow_chain(
            gworld_ptr,
            [int(x, 16) if isinstance(x, str) else int(x) for x in chain],
        )
        out["pawn_ptr"] = f"0x{pawn_ptr:X}"
    except MemoryReadError as exc:
        limits.append(f"pawn_chain_failed:{exc}")
        return out | {"limits": limits}

    fields = offsets.get("fields", {})
    root_off = fields.get("root_component")
    loc_off = fields.get("relative_location")
    if root_off is not None and loc_off is not None:
        try:
            root = mem.read_ptr(
                pawn_ptr + (int(root_off, 16) if isinstance(root_off, str) else root_off)
            )
            loc = mem.read_vector3(
                root + (int(loc_off, 16) if isinstance(loc_off, str) else loc_off)
            )
            out["position"] = loc.as_dict()
        except MemoryReadError:
            limits.append("position_read_failed")

    for name, off in (
        ("health", fields.get("health")),
        ("max_health", fields.get("max_health")),
        ("stamina", fields.get("stamina")),
        ("torpidity", fields.get("torpidity")),
        ("character_level", fields.get("character_level")),
    ):
        if off is None:
            continue
        try:
            o = int(off, 16) if isinstance(off, str) else int(off)
            out["vitals"][name] = mem.read_f32(pawn_ptr + o)
        except MemoryReadError:
            limits.append(f"{name}_read_failed")

    return out | {"limits": limits}


def build_digest(gate: GateResult, player: dict, offsets: dict) -> dict:
    return {
        "schema": "ark_sp_memory_digest.v0.1",
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
        "vitals_snapshot": {
            "position": player.get("position"),
            "vitals": player.get("vitals", {}),
        },
        "limits": player.get("limits", []),
    }


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
            player = read_player_slice(mem, offsets)
            digest = build_digest(gate, player, offsets)
            write_outputs(digest)
            pos = (player.get("position") or {})
            print(
                f"memory_digest ok pid={gate.pid} be_off={gate.battleye_disabled} "
                f"pos={pos.get('x', '?')},{pos.get('y', '?')},{pos.get('z', '?')} "
                f"limits={','.join(player.get('limits') or []) or 'none'}",
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
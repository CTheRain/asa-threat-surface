#!/usr/bin/env python3
"""Poll Snow Owl encapsulate/freeze state — SP lab."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from asa_memory_process import ASAMemoryProcess, MemoryReadError
from asa_memory_reader import (
    DEFAULT_OFFSETS,
    _parse_off,
    _read_bit_bool,
    _read_dino_mount_snapshot,
    _read_movement_state,
    _read_owl_abilities_snapshot,
    _read_shoulder_attach_snapshot,
    _resolve_chain,
    load_offsets,
)
from asa_sp_gate import verify_singleplayer

OUT = SCRIPT_DIR.parent / "snow_owl_freeze_poll.jsonl"

STATUS_FREEZE_VALUES = 0xBB4


def probe(offsets_path: Path) -> dict:
    gate = verify_singleplayer()
    if not gate.ok:
        raise SystemExit(f"SP gate blocked: {gate.reasons}")

    offsets = load_offsets(offsets_path)
    mem = ASAMemoryProcess()
    gworld = mem.resolve_gworld(offsets)
    if not gworld:
        raise SystemExit("GWorld unresolved")

    pawn = _resolve_chain(mem, gworld, "local_player_pawn", offsets)
    if not pawn:
        raise SystemExit("pawn chain failed")

    fields = offsets.get("fields") or {}
    pos = None
    root_off = _parse_off(fields.get("root_component"))
    loc_off = _parse_off(fields.get("relative_location"))
    if root_off is not None and loc_off is not None:
        try:
            root = mem.read_ptr(pawn + root_off)
            loc = mem.read_vector3(root + loc_off)
            pos = loc.as_dict()
        except MemoryReadError:
            pass

    movement, _ = _read_movement_state(mem, pawn, fields)
    dino_mount, _ = _read_dino_mount_snapshot(mem, pawn, fields)
    shoulder, _ = _read_shoulder_attach_snapshot(mem, pawn, fields)

    status_ptr = _resolve_chain(mem, pawn, "player_status_component", offsets)
    freeze_status = None
    if status_ptr:
        freeze_status = _read_bit_bool(mem, status_ptr, STATUS_FREEZE_VALUES, 0)

    owl, _ = _read_owl_abilities_snapshot(mem, pawn, offsets, dino_mount=dino_mount)

    return {
        "pawn_ptr": f"0x{pawn:X}",
        "position": pos,
        "pos_z": (pos or {}).get("z"),
        "movement_mode": movement.get("movement_mode_raw"),
        "custom_movement_mode": movement.get("custom_movement_mode"),
        "rider_index": dino_mount.get("rider_weak_index"),
        "mounted": bool(dino_mount.get("has_rider")),
        "owl_applicable": owl.get("applicable"),
        "encapsulate_is_active": owl.get("encapsulate_is_active"),
        "ice_crash_is_active": owl.get("ice_crash_is_active"),
        "freeze_status_values": freeze_status,
        "attach_child_count": shoulder.get("attach_child_count"),
        "attach_child_ptrs": shoulder.get("attach_child_ptrs"),
    }


def _sig(row: dict) -> str:
    return "|".join(
        [
            str(row.get("encapsulate_is_active")),
            str(row.get("ice_crash_is_active")),
            str(row.get("freeze_status_values")),
            str(row.get("movement_mode")),
            str(row.get("attach_child_count")),
            str(row.get("pos_z")),
        ]
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=0.3)
    parser.add_argument("--duration", type=float, default=90.0)
    parser.add_argument("--offsets", type=Path, default=DEFAULT_OFFSETS)
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    prev_sig = None
    start = time.monotonic()
    with args.out.open("a", encoding="utf-8") as fh:
        while time.monotonic() - start < args.duration:
            ts = datetime.now(timezone.utc).isoformat()
            try:
                report = probe(args.offsets)
            except SystemExit as exc:
                line = {"ts": ts, "error": str(exc)}
                fh.write(json.dumps(line) + "\n")
                fh.flush()
                time.sleep(args.interval)
                continue

            sig = _sig(report)
            changed = sig != prev_sig
            prev_sig = sig
            row = {"ts": ts, "changed": changed, **report}
            if changed:
                row["transition"] = True
            fh.write(json.dumps(row) + "\n")
            fh.flush()
            if changed:
                print(json.dumps(row), flush=True)
            time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
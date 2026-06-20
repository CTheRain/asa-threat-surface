#!/usr/bin/env python3
"""Poll shoulder probe fields and log transitions — SP lab."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from asa_shoulder_probe import DEFAULT_OFFSETS, probe

OUT = SCRIPT_DIR.parent / "shoulder_poll.jsonl"


def _sig(report: dict) -> str:
    weak = (report.get("weak_fields") or {}).get("mounted_dino_weak") or {}
    serial = weak.get("as_index_serial") or {}
    children = report.get("attach_children") or []
    child_ptrs = ",".join(
        (c.get("scene_component_ptr") or "?") for c in children[:8]
    )
    mount = report.get("shoulder_mount") or {}
    return "|".join(
        [
            str(serial.get("index")),
            str(serial.get("serial")),
            str(len(children)),
            child_ptrs,
            str(mount.get("mount_state")),
            str(report.get("has_shoulder_creature")),
        ]
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=float, default=1.5)
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
            shoulder_mount = report.get("shoulder_mount") or {}
            row = {
                "ts": ts,
                "changed": changed,
                "mount_state": shoulder_mount.get("mount_state"),
                "has_shoulder_creature": report.get("has_shoulder_creature"),
                "has_lantern_pet_mounted": shoulder_mount.get("has_lantern_pet_on_shoulder"),
                "has_lantern_pet_grounded": shoulder_mount.get("has_lantern_pet_grounded"),
                "mounted_dino_index": (report.get("weak_fields") or {})
                .get("mounted_dino_weak", {})
                .get("as_index_serial", {})
                .get("index"),
                "mounted_dino_serial": (report.get("weak_fields") or {})
                .get("mounted_dino_weak", {})
                .get("as_index_serial", {})
                .get("serial"),
                "attach_child_count": len(report.get("attach_children") or []),
                "attach_child_ptrs": [
                    c.get("scene_component_ptr")
                    for c in (report.get("attach_children") or [])
                ],
                "candidates": len(report.get("nearby_shoulder_candidates") or []),
            }
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
#!/usr/bin/env python3
"""Interactive SP offset mapper — read-only pymem scans, exports memory_offsets.json.

Workflow:
  1. guide (or scan/rescan/pointers/pick/export/verify)
  2. Change in-game values when prompted
  3. Export draft offsets → validate with memory reader
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from asa_memory_scanner import (
    MemoryScanError,
    attach,
    build_chain_from_ref,
    find_pointers_to,
    read_f32_at,
    rescan_f32,
    resolve_module,
    scan_f32,
)
from asa_sp_gate import SingleplayerGateError, verify_singleplayer

DEFAULT_OUT_DIR = SCRIPT_DIR.parent
OUT_DIR = Path(os.environ.get("ARK_LIVE_DATA", DEFAULT_OUT_DIR))
CONFIG_DIR = OUT_DIR / "config"
STATE_FILE = CONFIG_DIR / "offset_scan_state.json"
OFFSETS_FILE = CONFIG_DIR / "memory_offsets.json"
TEMPLATE_FILE = SCRIPT_DIR.parent / "templates" / "memory_offsets.template.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_out_dir(path: Path) -> None:
    global OUT_DIR, CONFIG_DIR, STATE_FILE, OFFSETS_FILE
    OUT_DIR = path
    CONFIG_DIR = OUT_DIR / "config"
    STATE_FILE = CONFIG_DIR / "offset_scan_state.json"
    OFFSETS_FILE = CONFIG_DIR / "memory_offsets.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"schema": "ark_offset_scan_state.v0.1", "fields": {}, "candidates": {}, "notes": []}


def save_state(state: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_offsets() -> dict:
    if OFFSETS_FILE.exists():
        return json.loads(OFFSETS_FILE.read_text(encoding="utf-8"))
    if TEMPLATE_FILE.exists():
        return json.loads(TEMPLATE_FILE.read_text(encoding="utf-8"))
    return {"schema": "ark_sp_memory_offsets.v0.1", "GWorld": None, "chains": {}, "fields": {}}


def save_offsets(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    OFFSETS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def require_gate() -> None:
    verify_singleplayer(strict=True)


def _prompt_float(label: str) -> float:
    raw = input(f"{label}: ").strip()
    return float(raw)


def _pick_address(candidates: list[int], label: str) -> int | None:
    if not candidates:
        print(f"No candidates for {label}.")
        return None
    if len(candidates) == 1:
        print(f"Single candidate for {label}: 0x{candidates[0]:X}")
        return candidates[0]
    print(f"\n{label}: {len(candidates)} candidates — showing first 25")
    for i, addr in enumerate(candidates[:25]):
        print(f"  [{i}] 0x{addr:X}")
    raw = input("Pick index (or Enter to skip): ").strip()
    if not raw:
        return None
    idx = int(raw)
    return candidates[idx]


def cmd_scan(args: argparse.Namespace) -> int:
    require_gate()
    pm = attach()
    value = args.value if args.value is not None else _prompt_float("Enter current in-game float value")
    print(f"Scanning for float ~{value} (epsilon={args.epsilon})...", flush=True)
    candidates = scan_f32(
        pm,
        value,
        epsilon=args.epsilon,
        heap_first=not args.all_regions,
        include_large_regions=args.all_regions,
        progress=True,
    )
    state = load_state()
    bucket = state.setdefault("candidates", {})
    bucket[args.field] = candidates
    state.setdefault("fields", {})[args.field] = {"last_scan_value": value}
    save_state(state)
    print(f"Found {len(candidates)} candidates for {args.field}.")
    if candidates:
        print(f"  sample: 0x{candidates[0]:X} ... 0x{candidates[-1]:X}")
    print("Change the value in-game, then: rescan", args.field)
    return 0


def cmd_rescan(args: argparse.Namespace) -> int:
    require_gate()
    pm = attach()
    state = load_state()
    candidates = state.get("candidates", {}).get(args.field) or []
    if not candidates:
        print(f"No prior scan for {args.field}. Run: scan {args.field}")
        return 1
    value = args.value if args.value is not None else _prompt_float("Enter NEW in-game float value")
    print(f"Rescanning {len(candidates)} candidates for ~{value}...", flush=True)
    narrowed = rescan_f32(pm, candidates, value, epsilon=args.epsilon)
    state["candidates"][args.field] = narrowed
    state.setdefault("fields", {})[args.field] = {
        **state.get("fields", {}).get(args.field, {}),
        "last_rescan_value": value,
        "count": len(narrowed),
    }
    save_state(state)
    print(f"Narrowed to {len(narrowed)} candidates.")
    if len(narrowed) <= 30:
        for addr in narrowed:
            print(f"  0x{addr:X} = {read_f32_at(pm, addr)}")
    return 0


def cmd_pointers(args: argparse.Namespace) -> int:
    require_gate()
    pm = attach()
    state = load_state()
    candidates = state.get("candidates", {}).get(args.field) or []
    if not candidates:
        print(f"No candidates for {args.field}.")
        return 1
    addr = args.address or _pick_address(candidates, args.field)
    if addr is None:
        return 1
    module_base, module_size = resolve_module(pm)
    print(f"Pointer scan to 0x{addr:X} ...", flush=True)
    refs = find_pointers_to(
        pm,
        addr,
        max_field_offset=args.max_offset,
        module_base=module_base,
        module_size=module_size,
        limit=args.limit,
    )
    state.setdefault("fields", {})[args.field]["target_address"] = hex(addr)
    state["fields"][args.field]["pointer_refs"] = [
        {"holder": hex(r.holder), "field_offset": hex(r.field_offset)} for r in refs
    ]
    save_state(state)
    print(f"Found {len(refs)} pointer refs.")
    for i, ref in enumerate(refs[:20]):
        chain = build_chain_from_ref(pm, ref, module_base=module_base)
        chain_txt = " -> ".join(chain) if chain else "(no static chain)"
        print(f"  [{i}] holder=0x{ref.holder:X} off={ref.field_offset:#x} chain={chain_txt}")
    return 0


def cmd_pick(args: argparse.Namespace) -> int:
    state = load_state()
    field_state = state.get("fields", {}).get(args.field) or {}
    refs_raw = field_state.get("pointer_refs") or []
    if not refs_raw:
        candidates = state.get("candidates", {}).get(args.field) or []
        addr = _pick_address(candidates, args.field)
        if addr is None:
            return 1
        offsets = load_offsets()
        offsets.setdefault("fields", {})[args.field] = hex(args.struct_offset or 0)
        state.setdefault("fields", {})[args.field]["absolute_address"] = hex(addr)
        save_offsets(offsets)
        save_state(state)
        print(f"Picked absolute address for {args.field}: 0x{addr:X}")
        print("For stable reloads, run pointers + pick with a pointer ref.")
        return 0

    print(f"Pointer refs for {args.field}:")
    for i, ref in enumerate(refs_raw[:20]):
        print(f"  [{i}] holder={ref['holder']} field_offset={ref['field_offset']}")
    raw = input("Pick ref index: ").strip()
    idx = int(raw)
    picked = refs_raw[idx]
    field_off = int(picked["field_offset"], 16)
    offsets = load_offsets()
    offsets.setdefault("fields", {})[args.field] = hex(field_off)
    save_offsets(offsets)
    state["fields"][args.field]["picked_ref"] = picked
    save_state(state)
    print(f"Saved fields.{args.field} = {hex(field_off)}")
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    require_gate()
    pm = attach()
    state = load_state()
    candidates = state.get("candidates", {}).get(args.field) or []
    if not candidates:
        print("No candidates to probe.")
        return 1
    addr = candidates[0] if len(candidates) == 1 else _pick_address(candidates, args.field)
    if addr is None:
        return 1
    print(f"Probing floats near 0x{addr:X} (+/- {args.radius} bytes):")
    start = addr - args.radius
    try:
        data = pm.read_bytes(start, args.radius * 2 + 4)
    except Exception as exc:
        print(f"Read failed: {exc}")
        return 1
    for rel in range(0, len(data) - 3, 4):
        value = struct.unpack_from("<f", data, rel)[0]
        if -1_000_000 < value < 1_000_000 and value == value:  # skip NaN
            abs_addr = start + rel
            mark = " <--" if abs_addr == addr else ""
            print(f"  0x{abs_addr:X} = {value:.4f}{mark}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    state = load_state()
    offsets = load_offsets()
    offsets["build_label"] = args.build or offsets.get("build_label") or "UNKNOWN_BUILD"
    offsets["mapped_at"] = utc_now()
    offsets["mapper_notes"] = state.get("notes", [])
    save_offsets(offsets)
    print(f"Exported {OFFSETS_FILE}")
    print(json.dumps(offsets, indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    require_gate()
    offsets = load_offsets()
    pm = attach()
    candidates = (load_state().get("candidates") or {}).get(args.field) or []
    if args.field in (offsets.get("fields") or {}):
        off = offsets["fields"][args.field]
        if candidates:
            addr = candidates[0]
            if isinstance(off, str):
                field_off = int(off, 16)
                base = addr - field_off
                print(f"{args.field}: base~0x{base:X} field_off={off}")
        print(f"Configured fields.{args.field} = {off}")
    for addr in candidates[:5]:
        val = read_f32_at(pm, addr)
        print(f"  candidate 0x{addr:X} -> {val}")
    return 0


def cmd_guide(_args: argparse.Namespace) -> int:
    print(
        """
=== ASA offset mapping guide (SP + -NoBattlEye) ===

You'll map ONE field first (health). Repeat for stamina/level after.

Steps:
  1. Note exact health from HUD
  2. scan health --value <HUD>
  3. Change health in-game (damage/food), then: rescan health --value <NEW>
  4. Repeat rescan until candidates <= ~10
  5. pointers health
  6. pick health
  7. probe health   (optional — spot nearby stamina offsets)
  8. export --build <your_patch_label>
  9. verify health

Tips:
  - If scan finds too many hits: use a weird exact value if you can (cheat set stat in SP)
  - pointers + pick stores struct field offset for memory_offsets.json
  - GWorld / pawn chain still need a second pass or Dumper-7 — ask for help when health is stable

Commands share state in config/offset_scan_state.json (local, gitignored).
"""
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ASA SP offset mapper (read-only)")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    sub = parser.add_subparsers(dest="command", required=True)

    p_guide = sub.add_parser("guide", help="Show step-by-step workflow")
    p_guide.set_defaults(func=cmd_guide)

    p_scan = sub.add_parser("scan", help="First float scan for a field")
    p_scan.add_argument("field", help="e.g. health, stamina")
    p_scan.add_argument("--value", type=float)
    p_scan.add_argument("--epsilon", type=float, default=0.05)
    p_scan.add_argument("--all-regions", action="store_true")
    p_scan.set_defaults(func=cmd_scan)

    p_rescan = sub.add_parser("rescan", help="Narrow candidates after value change")
    p_rescan.add_argument("field")
    p_rescan.add_argument("--value", type=float)
    p_rescan.add_argument("--epsilon", type=float, default=0.05)
    p_rescan.set_defaults(func=cmd_rescan)

    p_ptr = sub.add_parser("pointers", help="Find pointer refs to selected address")
    p_ptr.add_argument("field")
    p_ptr.add_argument("--address", type=lambda x: int(x, 0))
    p_ptr.add_argument("--max-offset", type=int, default=0x2000)
    p_ptr.add_argument("--limit", type=int, default=100)
    p_ptr.set_defaults(func=cmd_pointers)

    p_pick = sub.add_parser("pick", help="Save field offset from pointer ref or address")
    p_pick.add_argument("field")
    p_pick.add_argument("--struct-offset", type=lambda x: int(x, 0))
    p_pick.set_defaults(func=cmd_pick)

    p_probe = sub.add_parser("probe", help="Show nearby floats around a candidate")
    p_probe.add_argument("field")
    p_probe.add_argument("--radius", type=int, default=128)
    p_probe.set_defaults(func=cmd_probe)

    p_export = sub.add_parser("export", help="Write memory_offsets.json draft")
    p_export.add_argument("--build", type=str)
    p_export.set_defaults(func=cmd_export)

    p_verify = sub.add_parser("verify", help="Read back candidates vs config")
    p_verify.add_argument("field", default="health", nargs="?")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    configure_out_dir(args.out_dir)
    try:
        return args.func(args)
    except SingleplayerGateError as exc:
        print(f"SP GATE BLOCKED: {exc}", file=sys.stderr)
        return 2
    except MemoryScanError as exc:
        print(f"SCAN ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
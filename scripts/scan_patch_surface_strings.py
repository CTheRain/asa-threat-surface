#!/usr/bin/env python3
"""Scan ArkAscended.exe for patch-note keywords and cross-ref game-state catalog."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\ARK Survival Ascended"
    r"\ShooterGame\Binaries\Win64\ArkAscended.exe"
)
GAME_STATES_CSV = ROOT / "game-states" / "asa_game_states.csv"
CROSSWALK = ROOT / "live-data" / "bundles" / "item_creature_crosswalk_v2.csv"
OUT_DIR = ROOT / "patches" / "surface_scans"

# v88.22 patch note topics (extend per release)
PATCH_KEYWORDS = [
    "DinoStacking",
    "EnableDinoStackingDetection",
    "DinoStackingCheckRadius",
    "DinoStackingMaxOverlap",
    "DinoStackingChecksPerFrame",
    "PreventPlannedStructureDecayReset",
    "PlanningStructure",
    "PlannedStructure",
    "CryoFridge",
    "NearbyStructure",
    "StructureLimit",
    "QueenBee",
    "Hive",
    "Vault",
]


def find_offsets(data: bytes, needle: str) -> list[dict]:
    hits = []
    for enc, label in ((needle.encode("ascii"), "ascii"), (needle.encode("utf-16le"), "utf16le")):
        start = 0
        while True:
            idx = data.find(enc, start)
            if idx < 0:
                break
            hits.append({"encoding": label, "offset": f"0x{idx:X}"})
            start = idx + 1
    return hits


def catalog_has(keyword: str, csv_text: str) -> bool:
    return keyword.lower() in csv_text.lower()


def crosswalk_hits(keyword: str, csv_text: str) -> list[str]:
    rows = []
    for line in csv_text.splitlines():
        if keyword.lower() in line.lower():
            parts = line.split(",")
            if len(parts) > 4:
                rows.append(parts[3])  # class_ref column
    return sorted(set(rows))[:12]


def main() -> None:
    if not EXE.exists():
        raise SystemExit(f"Missing {EXE}")

    data = EXE.read_bytes()
    gs_text = GAME_STATES_CSV.read_text(encoding="utf-8", errors="replace") if GAME_STATES_CSV.exists() else ""
    cw_text = CROSSWALK.read_text(encoding="utf-8", errors="replace") if CROSSWALK.exists() else ""

    findings = []
    for kw in PATCH_KEYWORDS:
        offsets = find_offsets(data, kw)
        if not offsets:
            continue
        findings.append(
            {
                "keyword": kw,
                "exe_hits": offsets,
                "in_published_game_states_csv": catalog_has(kw, gs_text),
                "crosswalk_class_refs": crosswalk_hits(kw, cw_text),
            }
        )

    report = {
        "schema_version": 1,
        "scanned_at_utc": datetime.now(timezone.utc).isoformat(),
        "exe_path": str(EXE),
        "exe_size_bytes": EXE.stat().st_size,
        "exe_sha256": __import__("hashlib").sha256(data).hexdigest().upper(),
        "patch_keywords": PATCH_KEYWORDS,
        "findings": findings,
        "new_surface_candidates": [
            f["keyword"]
            for f in findings
            if not f["in_published_game_states_csv"]
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    out = OUT_DIR / f"patch_surface_{stamp}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    print(f"keywords hit: {len(findings)} | new vs catalog: {len(report['new_surface_candidates'])}")
    for kw in report["new_surface_candidates"]:
        print(f"  NEW: {kw}")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""Build enum catalog from Dumper-7 CppSDK struct headers (Phase C)."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SDK = (
    SCRIPT_DIR.parent
    / "dumps"
    / "sdk"
    / "5.5.4-817761+++ARK1+Rel-1.88-ShooterGame"
    / "CppSDK"
    / "SDK"
)
DEFAULT_OUT = SCRIPT_DIR.parent / "config" / "enum_catalog.json"

_ENUM_BLOCK_RE = re.compile(
    r"enum\s+class\s+(\w+)\s*:\s*(\w+)\s*\{([^}]*)\}",
    re.MULTILINE,
)
_ENUM_MEMBER_RE = re.compile(r"(\w+)\s*=\s*(-?0x[0-9A-Fa-f]+|-?\d+)", re.MULTILINE)

# Curated enums for live-state decoding (expand as game-states DB grows).
PRIORITY_ENUMS = {
    "ENetModeBP",
    "EPrimalCharacterStatusValue",
    "EMissionState",
    "ETravelFailure",
    "EPrimalCharacterInputType",
    "EMovementMode",
    "EPrimalEquipmentType",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_value(raw: str) -> int:
    raw = raw.strip()
    return int(raw, 16) if raw.lower().startswith(("0x", "-0x")) else int(raw)


def parse_enums_from_text(text: str) -> dict[str, dict]:
    enums: dict[str, dict] = {}
    for block in _ENUM_BLOCK_RE.finditer(text):
        name, underlying, body = block.group(1), block.group(2), block.group(3)
        members: dict[str, int] = {}
        for m in _ENUM_MEMBER_RE.finditer(body):
            members[m.group(1)] = _parse_value(m.group(2))
        if members:
            enums[name] = {"underlying": underlying, "members": members}
    return enums


def build_catalog(sdk_dir: Path, *, include_all: bool = False) -> dict:
    merged: dict[str, dict] = {}
    for path in sorted(sdk_dir.glob("*_structs.hpp")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for name, payload in parse_enums_from_text(text).items():
            if include_all or name in PRIORITY_ENUMS:
                merged[name] = payload

    reverse: dict[str, dict[str, str]] = {}
    for enum_name, payload in merged.items():
        rev = {str(v): k for k, v in payload["members"].items()}
        reverse[enum_name] = rev

    return {
        "schema": "ark_sp_enum_catalog.v0.2",
        "generated_at": utc_now(),
        "source_sdk": str(sdk_dir),
        "enums": merged,
        "reverse": reverse,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build ASA enum catalog from CppSDK")
    parser.add_argument("--sdk-dir", type=Path, default=DEFAULT_SDK)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--all", action="store_true", help="Include all enums (large)")
    args = parser.parse_args()

    catalog = build_catalog(args.sdk_dir, include_all=args.all)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    print(f"enums={list(catalog['enums'].keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Synthesize Dumper-7 Dumpspace JSON from an existing CppSDK tree.

Use when injection crashed after CppSDK but before DumpspaceGenerator finished.
Output is compatible with asa_dumper7_to_offsets.py --dump-dir .../Dumpspace.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SDK_ROOT = (
    SCRIPT_DIR.parent / "dumps" / "sdk" / "5.5.4-817761+++ARK1+Rel-1.88-ShooterGame"
)

_CLASS_RE = re.compile(
    r"\bclass\s+(?:alignas\([^)]+\)\s+)?(\w+)(?:\s+final)?\s*(?::|\{)",
)
_MEMBER_RE = re.compile(
    r"^\s+[\w:<>,\s\*&\[\]]+\s+(\w+)(?:\[[^\]]*\])?\s*;\s*//\s*(0x[0-9A-Fa-f]+)(?:\(0x([0-9A-Fa-f]+)\))?",
    re.MULTILINE,
)
_BASIC_OFFSET_RE = re.compile(
    r"^\s*constexpr\s+int32\s+(\w+)\s*=\s*(0x[0-9A-Fa-f]+|\d+);",
    re.MULTILINE,
)

_OFFSET_NAME_MAP = {
    "GObjects": "OFFSET_GOBJECTS",
    "AppendString": "OFFSET_APPENDSTRING",
    "GNames": "OFFSET_GNAMES",
    "GWorld": "OFFSET_GWORLD",
    "ProcessEvent": "OFFSET_PROCESSEVENT",
    "ProcessEventIdx": "INDEX_PROCESSEVENT",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_class_body(text: str, class_name: str) -> str | None:
    for match in _CLASS_RE.finditer(text):
        if match.group(1) != class_name:
            continue
        brace = text.find("{", match.end() - 1)
        if brace < 0:
            continue
        depth = 0
        for i in range(brace, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return text[brace : i + 1]
    return None


def parse_class_members(text: str, class_name: str) -> dict[str, tuple[int, int]]:
    body = _extract_class_body(text, class_name)
    if not body:
        return {}
    out: dict[str, tuple[int, int]] = {}
    for m in _MEMBER_RE.finditer(body):
        name, off_hex, size_hex = m.group(1), m.group(2), m.group(3)
        off = int(off_hex, 16)
        size = int(size_hex, 16) if size_hex else 4
        out.setdefault(name, (off, size))
    return out


def scan_sdk_classes(sdk_dir: Path) -> dict[str, dict[str, tuple[int, int]]]:
    classes: dict[str, dict[str, tuple[int, int]]] = {}
    for path in sorted(sdk_dir.glob("*_classes.hpp")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _CLASS_RE.finditer(text):
            cname = match.group(1)
            members = parse_class_members(text, cname)
            if not members:
                continue
            bucket = classes.setdefault(cname, {})
            for k, v in members.items():
                bucket.setdefault(k, v)
    return classes


def build_classes_info(classes: dict[str, dict[str, tuple[int, int]]]) -> list[dict]:
    entries: list[dict] = []
    for class_name in sorted(classes):
        member_list: list[dict] = []
        for member_name, (offset, size) in sorted(
            classes[class_name].items(), key=lambda x: x[1][0]
        ):
            member_list.append({member_name: ["void*", offset, size]})
        entries.append({class_name: member_list})
    return entries


def parse_basic_offsets(basic_hpp: Path) -> dict[str, int]:
    text = basic_hpp.read_text(encoding="utf-8", errors="replace")
    start = text.find("namespace Offsets")
    block = text[start:] if start >= 0 else text
    raw: dict[str, int] = {}
    for m in _BASIC_OFFSET_RE.finditer(block):
        name, val = m.group(1), m.group(2)
        raw[name] = int(val, 16) if val.lower().startswith("0x") else int(val)
    out: dict[str, int] = {"Dumper": 7}
    for k, v in raw.items():
        mapped = _OFFSET_NAME_MAP.get(k)
        if mapped:
            out[mapped] = v
    return out


def dumpspace_envelope(data) -> dict:
    return {
        "updated_at": utc_now(),
        "version": 10202,
        "credit": {
            "dumper_used": "Dumper-7",
            "dumper_link": "https://github.com/Encryqed/Dumper-7",
            "synthesized_by": "asa_cppsdk_to_dumpspace.py",
        },
        "data": data,
    }


def synthesize(version_dir: Path, out_dumpspace: Path | None = None) -> Path:
    sdk_dir = version_dir / "CppSDK" / "SDK"
    basic = sdk_dir / "Basic.hpp"
    if not sdk_dir.exists():
        raise FileNotFoundError(f"Missing CppSDK at {sdk_dir}")

    dumpspace = out_dumpspace or (version_dir / "Dumpspace")
    dumpspace.mkdir(parents=True, exist_ok=True)

    classes = scan_sdk_classes(sdk_dir)
    classes_info = build_classes_info(classes)
    offsets_info = parse_basic_offsets(basic) if basic.exists() else {"Dumper": 7}

    (dumpspace / "ClassesInfo.json").write_text(
        json.dumps(dumpspace_envelope(classes_info), indent=2),
        encoding="utf-8",
    )
    (dumpspace / "OffsetsInfo.json").write_text(
        json.dumps(dumpspace_envelope(offsets_info), indent=2),
        encoding="utf-8",
    )
    # Stubs so tooling expecting full Dumpspace set does not fail
    for name in ("FunctionsInfo.json", "StructsInfo.json", "EnumsInfo.json"):
        (dumpspace / name).write_text(
            json.dumps(dumpspace_envelope([]), indent=2),
            encoding="utf-8",
        )
    return dumpspace


def main() -> int:
    parser = argparse.ArgumentParser(description="CppSDK -> Dumpspace JSON synthesizer")
    parser.add_argument("--version-dir", type=Path, default=DEFAULT_SDK_ROOT)
    parser.add_argument("--out", type=Path, help="Dumpspace output dir (default: <version>/Dumpspace)")
    args = parser.parse_args()

    out = synthesize(args.version_dir, args.out)
    classes = json.loads((out / "ClassesInfo.json").read_text())["data"]
    print(f"wrote {out}")
    print(f"classes={len(classes)}")
    print(f"offsets={list(json.loads((out / 'OffsetsInfo.json').read_text())['data'].keys())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
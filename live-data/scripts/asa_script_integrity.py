#!/usr/bin/env python3
"""Verify research script SHA256 hashes against the committed manifest.

Deters casual/local tampering before live attach. Not DRM — determined users can
still edit both scripts and manifest. Use GitHub Releases + this check for community.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MANIFEST = SCRIPT_DIR / "script_integrity_manifest.json"

WATCHED = (
    "asa_memory_reader.py",
    "asa_memory_process.py",
    "asa_memory_scanner.py",
    "asa_offset_mapper.py",
    "asa_sp_gate.py",
    "asa_game_state_monitor.py",
    "asa_network_audit.py",
    "asa_safety_preflight.py",
    "asa_script_integrity.py",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest() -> dict:
    files: dict[str, str] = {}
    for name in WATCHED:
        path = SCRIPT_DIR / name
        if path.exists():
            files[name] = sha256_file(path)
    return {
        "schema": "ark_script_integrity.v0.1",
        "files": files,
    }


def verify_manifest(manifest_path: Path = MANIFEST) -> tuple[bool, list[str]]:
    if not manifest_path.exists():
        return False, [f"missing manifest: {manifest_path}"]
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected: dict[str, str] = data.get("files", {})
    errors: list[str] = []
    for name, want in expected.items():
        path = SCRIPT_DIR / name
        if not path.exists():
            errors.append(f"missing script: {name}")
            continue
        got = sha256_file(path)
        if got != want:
            errors.append(f"hash mismatch: {name} (file was modified)")
    for name in WATCHED:
        if name not in expected and (SCRIPT_DIR / name).exists():
            errors.append(f"not in manifest: {name}")
    return len(errors) == 0, errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Research script integrity")
    parser.add_argument("--write", action="store_true", help="regenerate manifest (maintainers)")
    parser.add_argument("--verify", action="store_true", help="verify against manifest")
    args = parser.parse_args()

    if args.write:
        manifest = build_manifest()
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {MANIFEST} ({len(manifest['files'])} files)")
        return 0

    ok, errors = verify_manifest()
    if ok:
        print("Script integrity OK")
        return 0
    print("SCRIPT INTEGRITY FAILED — refusing to run modified tooling:", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    print(
        "\nRestore from GitHub or re-clone. Do not run modified memory tooling on live ASA.",
        file=sys.stderr,
    )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
#!/usr/bin/env python3
"""Community safety preflight — run before memory reader or sharing tooling.

Checks offline: gate fixtures, no-network imports in research scripts, read-only pymem usage.
Does not attach to ArkAscended.exe.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

# Integrity check imported lazily to avoid circular imports during manifest regen.
RESEARCH_SCRIPTS = (
    "asa_memory_reader.py",
    "asa_memory_process.py",
    "asa_memory_scanner.py",
    "asa_offset_mapper.py",
    "asa_sp_gate.py",
    "asa_game_state_monitor.py",
    "asa_network_audit.py",
)

FORBIDDEN_IMPORT_ROOTS = {
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "http",
    "ftplib",
    "smtplib",
}

FORBIDDEN_CALLS = {
    "connect",
    "sendto",
    "send",
    "urlopen",
}

FORBIDDEN_PYMEM_WRITES = {
    "write_bytes",
    "write_int",
    "write_float",
    "write_string",
    "write_double",
    "write_char",
    "write_short",
    "write_long",
}


def _scan_script(path: Path) -> list[str]:
    issues: list[str] = []
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    issues.append(f"{path.name}: forbidden import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in FORBIDDEN_IMPORT_ROOTS:
                    issues.append(f"{path.name}: forbidden import from {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            if name in FORBIDDEN_CALLS:
                issues.append(f"{path.name}: suspicious call {name}()")
            if name in FORBIDDEN_PYMEM_WRITES:
                issues.append(f"{path.name}: forbidden pymem write call {name}()")

    if path.name == "asa_memory_process.py":
        if "read_bytes" not in text:
            issues.append(f"{path.name}: expected read_* pymem helpers")

    return issues


def _run_gate_tests() -> tuple[bool, str]:
    test_file = SCRIPT_DIR / "test_asa_sp_gate.py"
    proc = subprocess.run(
        [sys.executable, str(test_file)],
        capture_output=True,
        text=True,
        cwd=str(SCRIPT_DIR),
    )
    if proc.returncode == 0:
        return True, proc.stdout.strip() or "gate tests passed"
    return False, (proc.stdout + proc.stderr).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="ASA research tooling safety preflight")
    parser.add_argument("--json", action="store_true", help="machine-readable summary")
    args = parser.parse_args()

    findings: list[str] = []
    checks: dict[str, bool] = {}

    for name in RESEARCH_SCRIPTS:
        path = SCRIPT_DIR / name
        if not path.exists():
            findings.append(f"missing script: {name}")
            checks[f"script:{name}"] = False
            continue
        script_issues = _scan_script(path)
        checks[f"script:{name}"] = len(script_issues) == 0
        findings.extend(script_issues)

    gate_ok, gate_msg = _run_gate_tests()
    checks["gate_tests"] = gate_ok
    if not gate_ok:
        findings.append(f"gate tests failed: {gate_msg}")

    try:
        from asa_script_integrity import verify_manifest

        integrity_ok, integrity_errors = verify_manifest()
        checks["script_integrity"] = integrity_ok
        if not integrity_ok:
            findings.extend(integrity_errors)
    except Exception as exc:  # pragma: no cover
        checks["script_integrity"] = False
        findings.append(f"integrity check error: {exc}")

    try:
        import psutil  # noqa: F401
        checks["deps:psutil"] = True
    except ImportError:
        checks["deps:psutil"] = False
        findings.append("psutil not installed (pip install -r live-data/requirements-memory.txt)")

    try:
        import pymem  # noqa: F401
        checks["deps:pymem"] = True
    except ImportError:
        checks["deps:pymem"] = False
        findings.append("pymem not installed (pip install -r live-data/requirements-memory.txt)")

    ok = len(findings) == 0
    summary = {
        "schema": "ark_safety_preflight.v0.1",
        "ok": ok,
        "checks": checks,
        "findings": findings,
        "community_rules": [
            "Singleplayer only — never official or player-hosted servers",
            "Launch with -NoBattlEye before running memory reader",
            "Do not modify research scripts — integrity manifest must match",
            "Run START_NETWORK_AUDIT.ps1 alongside first live session",
            "Fill memory_offsets.json locally per patch — never commit it",
        ],
    }

    if args.json:
        import json

        print(json.dumps(summary, indent=2))
    else:
        print("ASA research tooling — safety preflight")
        print("=" * 48)
        for key, passed in checks.items():
            print(f"  [{'OK' if passed else 'FAIL'}] {key}")
        if findings:
            print("\nFindings:")
            for item in findings:
                print(f"  - {item}")
        else:
            print("\nAll offline checks passed.")
        print("\nBefore live attach:")
        for rule in summary["community_rules"]:
            print(f"  * {rule}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
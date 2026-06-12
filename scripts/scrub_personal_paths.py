#!/usr/bin/env python3
"""Redact local username and S: drive paths for public release."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REPLACEMENTS = [
    (re.compile(r"C:\\Users\\SLAANESH", re.IGNORECASE), r"C:\\Users\\<user>"),
    (re.compile(r"C:/Users/SLAANESH", re.IGNORECASE), r"C:/Users/<user>"),
    (re.compile(r"S:(?:\\|/)+ARK_LiveData", re.IGNORECASE), r"<local-data>/ARK_LiveData"),
    (re.compile(r"S:(?:\\|/)+ARK_ThreatSurface", re.IGNORECASE), r"<local-data>/ARK_ThreatSurface"),
    (re.compile(r"S:(?:\\|/)+ARK_GameStates", re.IGNORECASE), r"<local-data>/ARK_GameStates"),
]


def scrub_text(text: str) -> str:
    for pattern, repl in REPLACEMENTS:
        text = pattern.sub(repl, text)
    # JSON manifests often double-escape Windows paths.
    json_path_replacements = {
        "C:\\\\Users\\\\SLAANESH": "C:\\\\Users\\\\<user>",
        "C:\\Users\\SLAANESH": "C:\\Users\\<user>",
        "S:\\\\ARK_LiveData": "<local-data>\\\\ARK_LiveData",
        "S:\\\\ARK_ThreatSurface": "<local-data>\\\\ARK_ThreatSurface",
        "S:\\\\ARK_GameStates": "<local-data>\\\\ARK_GameStates",
    }
    for old, new in json_path_replacements.items():
        text = text.replace(old, new)
    return text


def scrub_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = scrub_text(original)
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        return True
    return False


def main() -> None:
    patterns = ("*.csv", "*.json", "*.md", "*.py", "*.ps1", "*.txt", "*.html")
    changed: list[str] = []
    for pattern in patterns:
        for path in ROOT.rglob(pattern):
            if ".git" in path.parts or path.name == "scrub_personal_paths.py":
                continue
            if scrub_file(path):
                changed.append(str(path.relative_to(ROOT)))
    print(f"Scrubbed {len(changed)} files")
    for name in changed:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
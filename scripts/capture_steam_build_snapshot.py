#!/usr/bin/env python3
"""Capture ASA Steam build metadata + key file fingerprints for patch diffing.

Uses local Steam client data (no SteamDB API):
  - steamapps/appmanifest_2399830.acf
  - depotcache/*_*.manifest (when present)
  - Selected ShooterGame file SHA256 + size
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

APP_ID = 2399830
MAIN_DEPOT = 2399831

STEAM_ROOT = Path(r"C:\Program Files (x86)\Steam")
MANIFEST_ACF = STEAM_ROOT / "steamapps" / f"appmanifest_{APP_ID}.acf"
DEPOT_CACHE = STEAM_ROOT / "depotcache"
GAME_ROOT = STEAM_ROOT / "steamapps" / "common" / "ARK Survival Ascended"

KEY_FILES = [
    "ShooterGame/Binaries/Win64/ArkAscended.exe",
    "ShooterGame/Content/Paks/global.ucas",
    "ShooterGame/Content/Paks/global.utoc",
    "ShooterGame/Content/Paks/pakchunk0-Windows.pak",
    "ShooterGame/Content/Paks/pakchunk0-Windows.ucas",
    "ShooterGame/Content/Paks/pakchunk0-Windows.utoc",
]

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "patches" / "build_snapshots"


def sha256_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper(), path.stat().st_size


def parse_acf(path: Path) -> dict:
    """Minimal parser for steam appmanifest .acf (VDF-ish)."""
    text = path.read_text(encoding="utf-8", errors="replace")

    def q(key: str) -> str | None:
        m = re.search(rf'"{key}"\s*"([^"]*)"', text)
        return m.group(1) if m else None

    depots: dict[str, dict[str, str]] = {}
    for m in re.finditer(
        r'"(\d+)"\s*\{\s*"manifest"\s*"(\d+)"\s*"size"\s*"(\d+)"',
        text,
    ):
        depots[m.group(1)] = {"manifest": m.group(2), "size": m.group(3)}

    return {
        "AppState": {
            "buildid": q("buildid"),
            "LastUpdated": q("LastUpdated"),
            "BytesDownloaded": q("BytesDownloaded"),
            "InstalledDepots": depots,
        }
    }


def list_depot_manifests(depot_id: int) -> list[dict]:
    rows = []
    if not DEPOT_CACHE.exists():
        return rows
    for p in DEPOT_CACHE.glob(f"{depot_id}_*.manifest"):
        m = re.match(rf"{depot_id}_(\d+)\.manifest$", p.name)
        if not m:
            continue
        rows.append(
            {
                "depot_id": depot_id,
                "manifest_gid": m.group(1),
                "path": str(p),
                "size_bytes": p.stat().st_size,
                "mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    rows.sort(key=lambda r: r["mtime_utc"], reverse=True)
    return rows


def fingerprint_files() -> list[dict]:
    out = []
    for rel in KEY_FILES:
        p = GAME_ROOT / rel
        if not p.exists():
            out.append({"relative_path": rel, "missing": True})
            continue
        digest, size = sha256_file(p)
        out.append(
            {
                "relative_path": rel.replace("\\", "/"),
                "size_bytes": size,
                "sha256": digest,
            }
        )
    return out


def main() -> None:
    if not MANIFEST_ACF.exists():
        raise SystemExit(f"Missing {MANIFEST_ACF}")

    acf = parse_acf(MANIFEST_ACF)
    build_id = acf.get("AppState", {}).get("buildid", "unknown")
    depots = acf.get("AppState", {}).get("InstalledDepots", {})

    snapshot = {
        "schema_version": 1,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "app_id": APP_ID,
        "build_id": build_id,
        "last_updated_unix": acf.get("AppState", {}).get("LastUpdated"),
        "bytes_downloaded_last_patch": acf.get("AppState", {}).get("BytesDownloaded"),
        "installed_depots": depots,
        "depot_manifest_cache": list_depot_manifests(MAIN_DEPOT),
        "key_file_fingerprints": fingerprint_files(),
        "notes": [
            "SteamDB has no public API; use local appmanifest + depotcache for diffing.",
            "Compare two snapshots or two depot manifest GIDs after each patch.",
        ],
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"build_{build_id}.json"
    out.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    print(f"Wrote {out}")
    print(f"build_id={build_id} main_depot_manifests={len(snapshot['depot_manifest_cache'])}")


if __name__ == "__main__":
    main()
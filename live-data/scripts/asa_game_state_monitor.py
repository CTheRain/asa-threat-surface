#!/usr/bin/env python3
"""Singleplayer ASA game-state monitor — read-only disk-side observability.

Watches saves, profiles, ItemLog, ShooterGame.log, and PrimalConsole history.
Mirrors changes to S:\\ARK_LiveData and writes a live summary for testing sessions.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

ASA_SAVED = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\ARK Survival Ascended\ShooterGame\Saved"
)
OUT_DIR = Path(r"S:\ARK_LiveData")
STATE_FILE = OUT_DIR / "monitor_state.json"
LATEST_FILE = OUT_DIR / "monitor_latest.json"
EVENTS_FILE = OUT_DIR / "live_events.jsonl"
POLL_SECONDS = 3

WATCH_ROOTS = [
    ASA_SAVED / "SavedArksLocal",
    ASA_SAVED / "LocalProfiles",
    ASA_SAVED / "SaveGames",
    ASA_SAVED / "Logs" / "ItemLog",
    ASA_SAVED / "Config" / "Windows",
]

SINGLE_FILES = [
    ASA_SAVED / "Logs" / "ShooterGame.log",
]

LOG_SIGNAL_RE = re.compile(
    r"cheat|EnableCheats|Anti-?Cheat|BattlEye|Replication|NetDriver|Projectile|"
    r"HitReg|Damage|Authority|ServerMove|ClientMove|Exploit|Disconnect|"
    r"CHEAT FAILURE|UShooterCheatManager",
    re.I,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_transient_save_artifact(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith("-journal") or name.endswith(".tmp") or name.endswith(".temp")


def snapshot_file(path: Path) -> dict:
    stat = path.stat()
    return {"path": str(path), "size": stat.st_size, "mtime": stat.st_mtime}


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {
        "files": {},
        "log_offsets": {},
        "console_history": [],
        "session_started_at": utc_now(),
    }


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def write_latest(payload: dict) -> None:
    LATEST_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_event(event: dict) -> None:
    with EVENTS_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(event) + "\n")


def mirror_file(path: Path) -> Path:
    if "ItemLog" in str(path):
        bucket = "itemlog"
    elif "SavedArksLocal" in str(path):
        bucket = "saves"
    elif "LocalProfiles" in str(path) or "SaveGames" in str(path):
        bucket = "profiles"
    elif "Config" in str(path):
        bucket = "config"
    elif path.name == "ShooterGame.log":
        bucket = "gamelog"
    else:
        bucket = "other"
    dest_dir = OUT_DIR / bucket
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = dest_dir / f"{stamp}__{path.name}"
    shutil.copy2(path, dest)
    return dest


def parse_item_log(text: str) -> dict:
    blocks = []
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            if current:
                blocks.append(current)
            current = {"actor": line[1:-1], "fields": {}, "items": []}
            continue
        if current is None:
            continue
        if "=" in line and not line.startswith("Item"):
            key, value = line.split("=", 1)
            current["fields"][key.strip()] = value.strip()
        elif line.startswith("Item"):
            m = re.match(r"Item\d+=(.+?),\s*Count:\s*(\d+),\s*Quality:\s*(\d+)", line)
            if m:
                current["items"].append(
                    {"name": m.group(1), "count": int(m.group(2)), "quality": int(m.group(3))}
                )
    if current:
        blocks.append(current)
    player = next((b for b in blocks if "PlayerPawn" in b.get("actor", "")), None)
    return {
        "block_count": len(blocks),
        "player": player,
        "blocks": blocks[:5],
    }


def extract_profile_snapshot(path: Path) -> dict:
    data = path.read_bytes().decode("latin1", errors="ignore")
    creatures = []
    seen = set()
    for m in re.finditer(
        r"((?:Juvenile|Adult|Baby)\s+)?([^/\x00-\x1f]{2,80}?)\s*-\s*Lvl\s*(\d+)\s*\(([^)]+)\)",
        data,
    ):
        label = re.sub(r"^[\W_]+", "", m.group(0).strip())
        if label in seen:
            continue
        seen.add(label)
        creatures.append({
            "label": label,
            "level": int(m.group(3)),
            "species": m.group(4).strip(),
        })
    tribe_events = []
    for m in re.finditer(r".{0,40}(Tamed|killed|Claimed|Destroyed).{0,80}", data, re.I):
        s = re.sub(r"\s+", " ", "".join(ch if ch.isprintable() else "." for ch in m.group(0))).strip()
        if len(s) > 12 and s not in tribe_events:
            tribe_events.append(s)
    return {
        "creatures_found": len(creatures),
        "creatures_sample": creatures[:25],
        "tribe_events_sample": tribe_events[:20],
    }


def extract_world_snapshot(path: Path) -> dict:
    data = path.read_bytes().decode("latin1", errors="ignore")
    tribe_events = []
    for m in re.finditer(r"[\x20-\x7e]{8,120}(?:Tamed|killed|Lvl \d+)[\x20-\x7e]{0,80}", data):
        s = re.sub(r"\s+", " ", m.group(0)).strip()
        if s not in tribe_events:
            tribe_events.append(s)
        if len(tribe_events) >= 30:
            break
    return {
        "map": path.parent.name if path.parent.name != "SavedArksLocal" else path.stem,
        "tribe_events_sample": tribe_events[:20],
        "size_bytes": path.stat().st_size,
    }


def parse_console_history(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("HistoryBuffer="):
            lines.append(line.split("=", 1)[1])
    return lines


def tail_log_signals(path: Path, offset: int) -> tuple[list[str], int]:
    if not path.exists():
        return [], offset
    size = path.stat().st_size
    if size < offset:
        offset = 0
    with path.open("rb") as fh:
        fh.seek(offset)
        chunk = fh.read()
    new_offset = size
    if not chunk:
        return [], new_offset
    text = chunk.decode("utf-8", errors="replace")
    hits = []
    for line in text.splitlines():
        if LOG_SIGNAL_RE.search(line):
            hits.append(line.strip()[:500])
    return hits[-50:], new_offset


def detect_active_map(saved_root: Path) -> str | None:
    candidates = list(saved_root.rglob("*.ark"))
    if not candidates:
        return None
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    return latest.parent.name if latest.parent != saved_root else latest.stem


def process_change(path: Path, state: dict) -> dict:
    event = {
        "seen_at": utc_now(),
        "source": str(path),
        "kind": path.suffix.lower(),
        "name": path.name,
    }
    dest = mirror_file(path)
    event["mirror"] = str(dest)
    event["size"] = path.stat().st_size

    if path.suffix.lower() == ".log" and "ItemLog" in path.name:
        parsed = parse_item_log(path.read_text(encoding="utf-8", errors="replace"))
        parsed_path = dest.with_suffix(dest.suffix + ".json")
        parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        event["parsed_json"] = str(parsed_path)
        event["summary"] = {
            "block_count": parsed["block_count"],
            "player_name": (parsed.get("player") or {}).get("fields", {}).get("Name"),
            "player_level": None,
            "location": (parsed.get("player") or {}).get("fields", {}).get("Location"),
        }
        pname = event["summary"]["player_name"] or ""
        m = re.search(r"Lvl\s*(\d+)", pname)
        if m:
            event["summary"]["player_level"] = int(m.group(1))

    elif path.name == "PlayerLocalData.arkprofile":
        snap = extract_profile_snapshot(path)
        snap_path = dest.with_suffix(dest.suffix + ".snapshot.json")
        snap_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        event["summary"] = snap
        event["parsed_json"] = str(snap_path)

    elif path.suffix.lower() == ".ark":
        snap = extract_world_snapshot(path)
        snap_path = dest.with_suffix(dest.suffix + ".snapshot.json")
        snap_path.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        event["summary"] = snap
        event["parsed_json"] = str(snap_path)
        event["map"] = snap["map"]

    elif path.name == "PrimalConsole.ini":
        history = parse_console_history(path)
        prev = set(state.get("console_history", []))
        new_cmds = [c for c in history if c not in prev]
        state["console_history"] = history[-200:]
        event["summary"] = {"new_commands": new_cmds[-20:], "history_count": len(history)}

    return event


def main() -> int:
    parser = argparse.ArgumentParser(description="ASA singleplayer game-state monitor")
    parser.add_argument("--once", action="store_true", help="Single poll then exit")
    parser.add_argument("--poll", type=int, default=POLL_SECONDS, help="Poll interval seconds")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    latest = {
        "updated_at": utc_now(),
        "session_started_at": state.get("session_started_at"),
        "active_map": detect_active_map(ASA_SAVED / "SavedArksLocal"),
        "recent_events": [],
        "recent_log_signals": [],
        "recent_console_commands": [],
        "notes": [
            "Disk-side monitor only — does not inject or read in-memory GameState.",
            "Use for correlating tests with save/profile/log changes on S:.",
        ],
    }
    write_latest(latest)
    print(f"ASA game-state monitor -> {OUT_DIR}", flush=True)
    print(f"Active map hint: {latest['active_map']}", flush=True)

    while True:
        changed_events = []
        log_path = ASA_SAVED / "Logs" / "ShooterGame.log"
        offset = int(state.get("log_offsets", {}).get(str(log_path), 0))
        signals, new_offset = tail_log_signals(log_path, offset)
        if signals:
            state.setdefault("log_offsets", {})[str(log_path)] = new_offset
            for sig in signals:
                evt = {"seen_at": utc_now(), "kind": "gamelog_signal", "line": sig}
                changed_events.append(evt)
                latest["recent_log_signals"] = (latest.get("recent_log_signals", []) + [sig])[-30:]

        targets: list[Path] = []
        for root in WATCH_ROOTS:
            if root.exists():
                if root.is_file():
                    targets.append(root)
                else:
                    targets.extend(
                        p for p in root.rglob("*")
                        if p.is_file() and not is_transient_save_artifact(p)
                    )
        targets.extend(p for p in SINGLE_FILES if p.exists())

        for path in targets:
            if is_transient_save_artifact(path):
                continue
            try:
                snap = snapshot_file(path)
            except FileNotFoundError:
                continue
            key = snap["path"]
            prev = state["files"].get(key)
            if prev and prev["mtime"] == snap["mtime"] and prev["size"] == snap["size"]:
                continue
            try:
                event = process_change(path, state)
            except OSError as exc:
                event = {"seen_at": utc_now(), "source": str(path), "error": str(exc)}
            changed_events.append(event)
            state["files"][key] = snap
            if event.get("summary", {}).get("new_commands"):
                latest["recent_console_commands"] = event["summary"]["new_commands"]

        if changed_events:
            latest["updated_at"] = utc_now()
            latest["active_map"] = detect_active_map(ASA_SAVED / "SavedArksLocal")
            latest["recent_events"] = (latest.get("recent_events", []) + changed_events)[-40:]
            write_latest(latest)
            save_state(state)
            for event in changed_events:
                append_event(event)
                print(json.dumps(event, ensure_ascii=False), flush=True)
        elif args.once:
            save_state(state)
            write_latest(latest)
            break

        if args.once:
            break
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
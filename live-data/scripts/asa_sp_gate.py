"""Singleplayer-only gate for ARK: Survival Ascended memory reads.

Refuses to run when the session looks like dedicated server, multiplayer client,
or BattlEye-protected play. Read-only policy: this module never writes game memory.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

DEFAULT_ASA_SAVED = Path(
    r"C:\Program Files (x86)\Steam\steamapps\common\ARK Survival Ascended\ShooterGame\Saved"
)
ASA_SAVED = Path(os.environ.get("ARK_ASA_SAVED", DEFAULT_ASA_SAVED))

PROCESS_NAMES = {"ArkAscended.exe"}
FORBIDDEN_PROCESS_NAMES = {"ArkAscendedServer.exe", "ShooterGameServer.exe"}
BATTLEYE_PROCESS_NAMES = {"BEService.exe", "BattlEye.exe"}

JOIN_REMOTE_RE = re.compile(
    r"Joining\s+.*\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
    r"Official\s+Server|"
    r"Connected\s+to\s+.*:\d{4,5}",
    re.I,
)
BATTLEYE_ACTIVE_RE = re.compile(
    r"BattlEye.*(?:enabled|initialized|started)|"
    r"Initializing\s+with\s+BattlEye\s+Anti-?Cheat",
    re.I,
)
BATTLEYE_DISABLED_RE = re.compile(
    r"BattlEye.*(?:disabled|not\s+used)|"
    r"launch(?:ed)?\s+with\s+-NoBattlEye|"
    r"-NoBattlEye",
    re.I,
)
DEDICATED_CMD_RE = re.compile(r"-server\b|dedicated", re.I)


class SingleplayerGateError(RuntimeError):
    """Raised when memory access is not allowed for the current session."""


@dataclass
class GateResult:
    ok: bool
    process_name: str
    pid: int
    reasons: list[str]
    warnings: list[str]
    battleye_disabled: bool


def _find_asa_process() -> psutil.Process | None:
    if psutil is None:
        return None
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        name = (proc.info.get("name") or "").lower()
        if name in {n.lower() for n in FORBIDDEN_PROCESS_NAMES}:
            raise SingleplayerGateError(
                f"dedicated/server process detected: {proc.info.get('name')} (pid={proc.pid})"
            )
        if name in {n.lower() for n in PROCESS_NAMES}:
            return proc
    return None


def _check_cmdline(proc: psutil.Process) -> list[str]:
    issues: list[str] = []
    try:
        cmd = " ".join(proc.cmdline() or [])
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return ["could not read process command line"]
    if DEDICATED_CMD_RE.search(cmd):
        issues.append(f"dedicated/server command line flag: {cmd[:200]}")
    return issues


def _read_log_tail(saved_root: Path = ASA_SAVED, max_bytes: int = 256_000) -> str:
    log_path = saved_root / "Logs" / "ShooterGame.log"
    if not log_path.exists():
        return ""
    size = log_path.stat().st_size
    with log_path.open("rb") as fh:
        fh.seek(max(0, size - max_bytes))
        return fh.read().decode("utf-8", errors="replace")


def _check_log_tail(saved_root: Path = ASA_SAVED) -> list[str]:
    text = _read_log_tail(saved_root)
    if not text:
        return ["ShooterGame.log missing (cannot confirm session type)"]
    hits = []
    for line in text.splitlines()[-400:]:
        if JOIN_REMOTE_RE.search(line):
            hits.append(line.strip()[:240])
    return hits


def _check_battleye_disabled(
    proc: psutil.Process, saved_root: Path = ASA_SAVED
) -> tuple[bool, list[str], list[str]]:
    """Require BattlEye off: no BE service process and no active BE init in log/cmdline."""
    reasons: list[str] = []
    warnings: list[str] = []

    if psutil is not None:
        for be_proc in psutil.process_iter(["name"]):
            name = (be_proc.info.get("name") or "")
            if name in BATTLEYE_PROCESS_NAMES:
                reasons.append(f"BattlEye process running: {name} (pid={be_proc.pid})")

    try:
        cmd_parts = proc.cmdline() or []
        cmd = " ".join(cmd_parts)
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        cmd = ""
        warnings.append("could not read process command line for BattlEye check")

    cmd_has_no_be = any(part.lower() == "-nobattleye" for part in cmd_parts)
    if cmd_has_no_be:
        return True, reasons, warnings

    log_text = _read_log_tail(saved_root)
    if not log_text:
        reasons.append(
            "BattlEye status unknown (missing ShooterGame.log); launch SP with -NoBattlEye"
        )
        return False, reasons, warnings

    recent = log_text.splitlines()[-400:]
    disabled_hits = [ln.strip()[:240] for ln in recent if BATTLEYE_DISABLED_RE.search(ln)]
    active_hits = [ln.strip()[:240] for ln in recent if BATTLEYE_ACTIVE_RE.search(ln)]

    if active_hits and not disabled_hits:
        reasons.append("BattlEye appears active in ShooterGame.log")
        reasons.extend([f"log signal: {h}" for h in active_hits[:3]])
        return False, reasons, warnings

    if not disabled_hits and not cmd_has_no_be:
        reasons.append(
            "BattlEye not confirmed disabled; relaunch singleplayer with -NoBattlEye"
        )
        return False, reasons, warnings

    if disabled_hits:
        warnings.append("BattlEye disabled per log")
    return len(reasons) == 0, reasons, warnings


def _check_local_save_activity(saved_root: Path = ASA_SAVED) -> tuple[bool, str]:
    local = saved_root / "SavedArksLocal"
    if not local.exists():
        return False, "SavedArksLocal missing"
    arks = list(local.rglob("*.ark"))
    if not arks:
        return False, "no local .ark saves found"
    latest = max(arks, key=lambda p: p.stat().st_mtime)
    return True, f"local save present: {latest.parent.name}/{latest.name}"


def verify_singleplayer(*, strict: bool = True, saved_root: Path | None = None) -> GateResult:
    """Return gate result; raise SingleplayerGateError when strict and not SP-safe."""
    root = saved_root or ASA_SAVED
    reasons: list[str] = []
    warnings: list[str] = []

    if psutil is None:
        raise SingleplayerGateError("psutil required for SP gate: pip install psutil")

    proc = _find_asa_process()
    if proc is None:
        raise SingleplayerGateError("ArkAscended.exe not running")

    reasons.extend(_check_cmdline(proc))
    log_hits = _check_log_tail(root)
    if log_hits and not log_hits[0].startswith("ShooterGame.log"):
        reasons.extend([f"log signal: {h}" for h in log_hits[:5]])

    be_ok, be_reasons, be_notes = _check_battleye_disabled(proc, root)
    reasons.extend(be_reasons)
    warnings.extend(be_notes)

    ok_local, local_msg = _check_local_save_activity(root)
    warnings.append(local_msg if ok_local else f"warning: {local_msg}")

    ok = len(reasons) == 0
    result = GateResult(
        ok=ok,
        process_name=proc.name(),
        pid=proc.pid,
        reasons=reasons,
        warnings=warnings,
        battleye_disabled=be_ok,
    )
    if strict and not ok:
        raise SingleplayerGateError("; ".join(reasons))
    return result
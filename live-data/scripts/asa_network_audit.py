#!/usr/bin/env python3
"""Poll TCP/UDP endpoints for ASA + local research tooling — local log only.

No packets are captured or transmitted by this script. Uses psutil to list
connections owned by watched processes. Output stays under ARK_LIVE_DATA.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil
except ImportError:
    print("psutil required: pip install psutil", file=sys.stderr)
    raise SystemExit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = SCRIPT_DIR.parent
OUT_DIR = Path(os.environ.get("ARK_LIVE_DATA", DEFAULT_OUT_DIR))

WATCH_NAMES = {
    "arkascended.exe",
    "python.exe",
    "pythonw.exe",
    "beservice.exe",
    "battleye.exe",
}

# Our tooling modules — used to tag python PIDs
TOOL_MARKERS = (
    "asa_memory_reader.py",
    "asa_game_state_monitor.py",
    "asa_network_audit.py",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def configure_output_dir(path: Path) -> None:
    global OUT_DIR
    OUT_DIR = path


def _classify_addr(addr: str) -> str:
    if addr in {"127.0.0.1", "::1", "0.0.0.0", "*"}:
        return "loopback"
    if addr.startswith("10.") or addr.startswith("192.168.") or addr.startswith("169.254."):
        return "private"
    if addr.startswith("fe80:") or addr.startswith("fd"):
        return "private"
    parts = addr.split(".")
    if len(parts) == 4 and parts[0] == "172":
        try:
            second = int(parts[1])
            if 16 <= second <= 31:
                return "private"
        except ValueError:
            pass
    return "public"


def _redact_endpoint(ip: str, port: int) -> tuple[str, str]:
    """Never persist host LAN/WAN identity — port alone is enough for audit."""
    addr_class = _classify_addr(ip)
    if addr_class == "public":
        return f"{ip}:{port}", addr_class
    return f"<{addr_class}-redacted>:{port}", addr_class


def _tool_label(cmdline: list[str] | None) -> str | None:
    if not cmdline:
        return None
    joined = " ".join(cmdline).lower()
    for marker in TOOL_MARKERS:
        if marker.lower() in joined:
            return marker
    return None


def snapshot_connections() -> dict:
    rows: list[dict] = []
    seen: set[tuple] = set()
    processes: list[dict] = []

    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        name = (proc.info.get("name") or "").lower()
        if name not in WATCH_NAMES:
            continue
        tool = _tool_label(proc.info.get("cmdline"))
        processes.append(
            {
                "pid": proc.pid,
                "name": proc.info.get("name"),
                "tool": tool,
            }
        )
        try:
            conns = proc.net_connections(kind="inet")
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            processes[-1]["connections_error"] = "access_denied"
            continue

        for c in conns:
            if not c.raddr:
                continue
            remote_ip = c.raddr.ip
            remote_port = c.raddr.port
            key = (proc.pid, c.laddr, remote_ip, remote_port, c.type.name, c.status)
            if key in seen:
                continue
            seen.add(key)
            local_ep = None
            local_class = None
            if c.laddr:
                local_ep, local_class = _redact_endpoint(c.laddr.ip, c.laddr.port)
            remote_ep, remote_class = _redact_endpoint(remote_ip, remote_port)
            rows.append(
                {
                    "pid": proc.pid,
                    "process": proc.info.get("name"),
                    "tool": tool,
                    "local": local_ep,
                    "local_class": local_class,
                    "remote": remote_ep,
                    "remote_class": remote_class,
                    "type": c.type.name,
                    "status": c.status,
                }
            )

    public = [r for r in rows if r["remote_class"] == "public"]
    tool_public = [r for r in public if r.get("tool")]

    return {
        "schema": "ark_network_audit.v0.2",
        "captured_at": utc_now(),
        "processes_watched": processes,
        "connections": rows,
        "summary": {
            "total_connections": len(rows),
            "public_endpoints": len(public),
            "public_from_research_tools": len(tool_public),
            "research_tool_has_network": len(tool_public) > 0,
        },
        "notes": [
            "Game may still reach Steam/EOS in SP; this audit flags our Python tooling separately.",
            "Empty public_from_research_tools means asa_memory_reader/monitor sent no sockets.",
            "Local/private/loopback IPs are redacted at capture (<private-redacted>:port).",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Local connection audit for ASA SP research")
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    configure_output_dir(args.out_dir)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    latest = args.out_dir / "network_audit_latest.json"
    stream = args.out_dir / "network_audit.jsonl"

    while True:
        snap = snapshot_connections()
        latest.write_text(json.dumps(snap, indent=2), encoding="utf-8")
        with stream.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(snap) + "\n")

        s = snap["summary"]
        flag = "TOOL_NET!" if s["research_tool_has_network"] else "tools_clean"
        print(
            f"{snap['captured_at']} conns={s['total_connections']} "
            f"public={s['public_endpoints']} tool_public={s['public_from_research_tools']} [{flag}]",
            flush=True,
        )
        for row in snap["connections"]:
            if row["remote_class"] == "public":
                tool = row.get("tool") or row["process"]
                print(f"  public {tool} -> {row['remote']} ({row['status']})", flush=True)

        if args.once:
            return 1 if s["research_tool_has_network"] else 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
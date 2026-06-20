#!/usr/bin/env python3
"""Correlate disk-side live events with nearest memory stream samples (Phase F).

Appends correlated_events.jsonl and maintains correlated_latest.json.
Phase C decoder enriches each row via asa_state_decoder.decode_snapshot().
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from bisect import bisect_left
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from asa_state_decoder import decode_snapshot, load_catalog  # noqa: E402

DEFAULT_LIVE = SCRIPT_DIR.parent


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_ts(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00"))


def configure_paths(live_dir: Path) -> dict[str, Path]:
    return {
        "live": live_dir,
        "events": live_dir / "live_events.jsonl",
        "memory": live_dir / "memory_stream.jsonl",
        "out": live_dir / "correlated_events.jsonl",
        "latest": live_dir / "correlated_latest.json",
        "state": live_dir / "correlator_state.json",
    }


def load_state(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"last_event_line": 0, "memory_cache_line": 0}


def save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_memory_index(path: Path, start_line: int = 0) -> tuple[list[datetime], list[dict], int]:
    """Load memory samples from start_line; return (times, rows, total_lines)."""
    times: list[datetime] = []
    rows: list[dict] = []
    if not path.exists():
        return times, rows, start_line

    total = 0
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            total = i + 1
            if i < start_line or not line.strip():
                continue
            try:
                row = json.loads(line)
                ts = parse_ts(row["updated_at"])
                times.append(ts)
                rows.append(row)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return times, rows, total


def nearest_memory(
    event_ts: datetime,
    mem_times: list[datetime],
    mem_rows: list[dict],
    max_delta_ms: int,
) -> tuple[dict | None, int | None, str]:
    if not mem_times:
        return None, None, "no_memory_samples"

    idx = bisect_left(mem_times, event_ts)
    candidates: list[int] = []
    if idx < len(mem_times):
        candidates.append(idx)
    if idx > 0:
        candidates.append(idx - 1)

    best_i = None
    best_delta = None
    for i in candidates:
        delta = abs(int((mem_times[i] - event_ts).total_seconds() * 1000))
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_i = i

    if best_i is None or best_delta is None:
        return None, None, "no_candidate"

    quality = "nearest_sample"
    if best_delta > max_delta_ms:
        quality = "stale_sample"
    return mem_rows[best_i], best_delta, quality


def correlate_event(
    disk_event: dict,
    mem_digest: dict | None,
    delta_ms: int | None,
    quality: str,
    catalog: dict,
    max_delta_ms: int,
) -> dict:
    decoded = None
    if mem_digest:
        decoded = mem_digest.get("decoded_state") or decode_snapshot(mem_digest, catalog)
    within = delta_ms is not None and delta_ms <= max_delta_ms

    return {
        "schema": "ark_sp_correlated_event.v0.2",
        "correlated_at": utc_now(),
        "disk_event": disk_event,
        "memory": {
            "updated_at": mem_digest.get("updated_at") if mem_digest else None,
            "delta_ms": delta_ms,
            "offsets_build": mem_digest.get("offsets_build") if mem_digest else None,
            "state_snapshot": mem_digest.get("state_snapshot") if mem_digest else None,
            "decoded": decoded,
        },
        "correlation": {
            "method": "nearest_timestamp",
            "quality": quality,
            "delta_ms": delta_ms,
            "within_window": within,
            "max_window_ms": max_delta_ms,
        },
    }


def process_new_events(
    paths: dict[str, Path],
    *,
    max_delta_ms: int,
    catalog: dict,
    backfill: bool = False,
) -> int:
    state = load_state(paths["state"])
    if backfill:
        state["last_event_line"] = 0
        state["memory_cache_line"] = 0
        if paths["out"].exists():
            paths["out"].write_text("", encoding="utf-8")

    mem_start = 0 if backfill else state.get("memory_cache_line", 0)
    mem_times, mem_rows, mem_total = load_memory_index(paths["memory"], mem_start)

    # When incrementally extending cache, prepend prior samples for bisect.
    if not backfill and mem_start > 0 and paths["memory"].exists():
        prior_times, prior_rows, _ = load_memory_index(paths["memory"], 0)
        # Use full index for correctness (memory stream is small).
        mem_times, mem_rows, mem_total = prior_times, prior_rows, mem_total

    if not paths["events"].exists():
        return 0

    written = 0
    out_fh = paths["out"].open("a", encoding="utf-8")
    latest_rows: list[dict] = []

    try:
        with paths["events"].open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i < state["last_event_line"] or not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    event_ts = parse_ts(event["seen_at"])
                except (json.JSONDecodeError, KeyError, ValueError):
                    state["last_event_line"] = i + 1
                    continue

                mem, delta, quality = nearest_memory(
                    event_ts, mem_times, mem_rows, max_delta_ms
                )
                row = correlate_event(
                    event, mem, delta, quality, catalog, max_delta_ms
                )
                out_fh.write(json.dumps(row) + "\n")
                latest_rows.append(row)
                written += 1
                state["last_event_line"] = i + 1
    finally:
        out_fh.close()

    state["memory_cache_line"] = mem_total
    save_state(paths["state"], state)

    if latest_rows:
        summary = build_latest_summary(paths, latest_rows[-20:], written)
        paths["latest"].write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return written


def build_latest_summary(paths: dict[str, Path], recent: list[dict], batch_count: int) -> dict:
    matched = sum(
        1 for r in recent if r.get("correlation", {}).get("within_window")
    )
    stale = sum(
        1
        for r in recent
        if r.get("correlation", {}).get("quality") == "stale_sample"
    )
    return {
        "schema": "ark_sp_correlated_latest.v0.2",
        "updated_at": utc_now(),
        "batch_correlated": batch_count,
        "recent_events": recent,
        "stats": {
            "recent_count": len(recent),
            "within_window": matched,
            "stale_sample": stale,
        },
        "paths": {
            "correlated_events": str(paths["out"]),
            "live_events": str(paths["events"]),
            "memory_stream": str(paths["memory"]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Correlate disk events with memory stream")
    parser.add_argument(
        "--live-dir",
        type=Path,
        default=Path(os.environ.get("ARK_LIVE_DATA", DEFAULT_LIVE)),
    )
    parser.add_argument("--max-delta-ms", type=int, default=15_000)
    parser.add_argument("--backfill", action="store_true", help="Reprocess all live_events")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll", type=float, default=2.0)
    parser.add_argument("--catalog", type=Path, default=None)
    args = parser.parse_args()

    paths = configure_paths(args.live_dir)
    paths["live"].mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(args.catalog) if args.catalog else load_catalog()

    while True:
        n = process_new_events(
            paths,
            max_delta_ms=args.max_delta_ms,
            catalog=catalog,
            backfill=args.backfill,
        )
        if n:
            print(f"correlated {n} events -> {paths['out']}", flush=True)
        args.backfill = False

        if args.once:
            break
        time.sleep(args.poll)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
# Community Use Policy

Rules for anyone using `asa-threat-surface` research tooling from the public GitHub repo or Discord community links.

This is **not** a EULA and **not** legal advice. It states how the tooling is designed to be used and what we do **not** do with your machine.

---

## Who this is for

- Singleplayer researchers testing client-trust / persistence mechanics
- Community members following pinned **GitHub Releases** or `main` after maintainer testing
- People who accept **read-only, local-only** tooling with no multiplayer support

## Who this is not for

- Official server or player-hosted session play with memory tooling attached
- BattlEye-protected contexts
- Cheat development, raid intel, or anti-cheat evasion
- Anyone who needs guaranteed safety after **modifying** the scripts

---

## Required use conditions

| Rule | Detail |
|------|--------|
| **Singleplayer only** | Local tray / `SavedArksLocal` — not official, not dedicated |
| **BattlEye disabled** | Launch with `-NoBattlEye`; close other BattlEye-protected games |
| **Read-only** | Do not patch scripts to write game memory or bypass gates |
| **Official launchers** | Use `live-data/scripts/START_*.ps1` — they run preflight + integrity checks |
| **Acknowledgment** | Memory tools prompt `SP-ONLY` before live attach |
| **Pinned releases** | Prefer GitHub **Releases** tags over unverified forks |

---

## Privacy — no tracking

**We do not collect identity or usage telemetry.**

| We do **not** | Ever |
|---------------|------|
| Log Discord usernames, Steam IDs, or IPs | ✓ |
| Phone home or report who ran a script | ✓ |
| Require accounts or API keys in tooling | ✓ |
| Upload your saves, offsets, or memory digests to GitHub | ✓ |

All outputs (`memory_digest.json`, `monitor_latest.json`, `offset_scan_state.json`, etc.) stay **on your machine** under your `ARK_LIVE_DATA` path. You choose what to share in chat.

The game itself may still contact Steam/EOS in singleplayer — that is Wildcard/Valve, not this repo.

---

## Script integrity

Research scripts are checksummed in `live-data/scripts/script_integrity_manifest.json`.

- **Do not** hand-edit memory tooling and expect safety guarantees
- If preflight reports **integrity failed**, re-clone or restore from the official repo
- Maintainers regenerate the manifest after script changes:

```powershell
python live-data/scripts/asa_script_integrity.py --write
```

Forks that remove gates or integrity checks are **unsupported**.

---

## Your responsibility

You are responsible for how you use this software.

- Bypassing SP/BattlEye gates, editing scripts, or running on multiplayer can result in **game bans or account action** — that risk is yours
- Patch-specific offsets are your local config — wrong offsets read garbage; that is not a ban risk but can mislead testing
- This repo is research documentation and tooling, not a warranty of undetectability

**If you are unsure, do not attach memory tooling. Use disk-only tools** (`START_MONITOR.ps1`) first.

---

## What maintainers test before pointing the community at `main`

1. `START_PREFLIGHT.ps1` — AST safety + gate unit tests + integrity
2. SP gate blocks when game is not running or rules are violated
3. Network audit shows `research_tool_has_network: false` for Python tooling
4. No secrets, saves, or PII in committed files (`scripts/scrub_personal_paths.py`)

Live offset mapping per game patch is still **manual/community-local** until validated on the current build.

---

## Reporting issues

Report bugs or safety concerns via GitHub Issues on the official repo. Do not post `memory_offsets.json`, full saves, or digests with coordinates in public issues — describe behavior instead.

---

## Related docs

- [`SAFETY_BOUNDARY.md`](SAFETY_BOUNDARY.md) — git red lines, what never gets committed
- [`MEMORY_READER_SP.md`](MEMORY_READER_SP.md) — memory reader setup, mapper workflow, integrity
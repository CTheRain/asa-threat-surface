# asa-threat-surface

ARK Survival Ascended (ASA) **client-trust / threat-surface** research for **ARK Maker State Lab** assessment: static game-state catalogs, live single-player disk evidence, machine-queryable lookup packs, and **state capsules** for future patch regression.

```text
asa-threat-surface repo  =  current evidence map (pre-lab)
ARK Maker State Lab      =  future DLC-only SP reproduction chamber
toolkit swarm            =  refinery — chat sees verdict packets only
```

Abuse framing focuses on **client-trusted paths** (movement, projectiles, saves, persistence) — not cheat-brand strings in vanilla paks.

## What's in this repo

| Path | Contents |
|------|----------|
| `docs/` | **ARK Maker State Lab** plan spine (capsules, patch workflow, safety boundary) |
| `capsules/` | State tray manifests + verdict scaffolds (`capsule_000_survival_test` first) |
| `game-states/` | Enum catalogs from `ArkAscended.exe` + pak reconstruction (`EPrimalItemType`, `ECheatActorType`, …) |
| `live-data/scripts/` | Crosswalk builders, LLM lookup pack builder, SP save monitor, **SP memory reader** (BattlEye off) |
| `live-data/bundles/` | Session bundles, item/creature crosswalk v1/v2, drag-and-drop LLM lookup packs |
| `live-data/sources/mxcheatui/` | Key MxCheatUI spawn table extracts (for rebuild) |
| `threat-surface/` | Phase 1–2 indexes, cheat/intel CSVs, docs (not the ~258 GB pak mirror) |

## Quick start — LLM lookup (ChatGPT / Claude / Grok)

1. Attach `live-data/bundles/asa_game_lookup_quick_v1.json` (session-focused, ~220 KB) or `asa_game_lookup_v1.md` (full catalog).
2. Paste instructions from `live-data/bundles/asa_game_lookup_system_prompt_v1.txt`.
3. Ask: *"How do I give myself a Tek Rifle?"*, *"Blueprint for Oasisaur?"*, *"Was Tek Generator in the session save?"*

## Rebuild crosswalk + lookup pack

Requires local paths on `S:` (or adjust scripts):

```powershell
python live-data/scripts/build_item_creature_crosswalk.py
python live-data/scripts/build_asa_game_lookup_pack.py
```

MxCheatUI table inputs: `live-data/sources/mxcheatui/` or full unpack under `<local-data>/ARK_LiveData\bundles\_extract\`.

## Live SP monitor

```powershell
python live-data/scripts/asa_game_state_monitor.py
# or
./live-data/scripts/START_MONITOR.ps1
```

Mirrors saves/config to `<local-data>/ARK_LiveData\` (not committed — see `.gitignore`).

## Live SP memory reader (optional)

**Singleplayer only. BattlEye must be disabled** (`-NoBattlEye`). Read-only numeric vitals — no API calls, no tokens, no player names in output.

```powershell
$env:ARK_LIVE_DATA = "<local-data>\ARK_LiveData"   # optional
./live-data/scripts/START_MEMORY_READER.ps1
```

See [`docs/MEMORY_READER_SP.md`](docs/MEMORY_READER_SP.md), [`docs/COMMUNITY_USE_POLICY.md`](docs/COMMUNITY_USE_POLICY.md), and [`docs/SAFETY_BOUNDARY.md`](docs/SAFETY_BOUNDARY.md).

## Bridge mods (on-disk references)

| Mod | CurseForge | Role |
|-----|------------|------|
| MxCheatUI | 1028139 | Item/creature spawn datatables → blueprint crosswalk |
| GaiaCommands | 936457 | Admin asset search bridge |

## Session reference (The Center SP, 2026-06-11)

Validated in `live-data/bundles/session_20260611_center_combat_destruction_v1.json`:

- Activity: grapples, element, Tek Rifle structure/dino destruction
- Exit save SHA256 in bundle manifest (full `.ark` stays local on `S:`)
- Player/tribe names in bundle logs are **local research notes** — scrub before any public fork

## Local bulk data (not in git)

**Raw paks are never committed** — no `.pak`, `.ucas`, or `.utoc` files belong in this repository. Only derived indexes, CSVs, JSON catalogs, and small MxCheatUI table extracts.

Keep on `S:` and regenerate indexes as needed:

- `<local-data>/ARK_ThreatSurface\` — full IoStore mirror, meat string scan, retoc extracts
- `<local-data>/ARK_LiveData\saves\` — mirrored `.ark` / `.arkbak`
- `<local-data>/ARK_GameStates\` — working copy (this repo carries published snapshots)

## Browse online

After enabling GitHub Pages (Settings → Pages → Deploy from branch `main` / root), open:

**https://ctherain.github.io/asa-threat-surface/**

The `index.html` viewer has three tabs:

| Tab | What it does |
|-----|----------------|
| **Catalog** | Search items/creatures, blueprint paths, cheat templates (quick or full 2.5k pack) |
| **State Simulator** | Step through scenarios (craft, combat, tame, cheats) — enums → disk persistence layers |
| **Enum Explorer** | Pick `EPrimalItemType`, `ECheatActorType`, `EActorListsBP`, etc. → linked catalog rows |

Simulation data: `game-states/asa_game_states_sim.json` (rebuild with `python scripts/build_game_states_sim.py`).

## ARK Maker State Lab (capsules)

Evidence bridge — threat-surface proof becomes reproducible trays:

```text
observed behavior → evidence packet → ARK Maker capsule → Lua logger → patch verdict
```

| Doc | Purpose |
|-----|---------|
| [`docs/ARK_MAKER_STATE_LAB.md`](docs/ARK_MAKER_STATE_LAB.md) | Operating concept and two-layer model |
| [`docs/CAPSULE_SCHEMA.md`](docs/CAPSULE_SCHEMA.md) | `capsule_manifest.json` and state tray slots |
| [`docs/PATCH_DAY_WORKFLOW.md`](docs/PATCH_DAY_WORKFLOW.md) | Re-run matrix after game updates |
| [`docs/COMMUNITY_USE_POLICY.md`](docs/COMMUNITY_USE_POLICY.md) | Discord/public repo rules — SP-only, no tracking, your responsibility |
| [`docs/SAFETY_BOUNDARY.md`](docs/SAFETY_BOUNDARY.md) | Red lines (no raw saves/paks, no intel automation) |
| [`docs/MEMORY_READER_SP.md`](docs/MEMORY_READER_SP.md) | SP-only memory digest — BattlEye off, read-only |
| [`docs/STEAM_PATCH_DIFF.md`](docs/STEAM_PATCH_DIFF.md) | Steam buildid/manifest diff → exe surfaces → crosswalk |

First capsule: [`capsules/capsule_000_survival_test/`](capsules/capsule_000_survival_test/) — one Tek Rifle, save/reload survival check.

## License

Research / assessment artifacts. Game content © Studio Wildcard. Mod extracts © respective authors.
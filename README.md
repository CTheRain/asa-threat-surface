# asa-threat-surface

ARK Survival Ascended (ASA) **client-trust / threat-surface** research for Maker Lab–style assessment: static game-state catalogs, live single-player disk evidence, and machine-queryable item/creature lookup packs.

Abuse framing focuses on **client-trusted paths** (movement, projectiles, saves, persistence) — not cheat-brand strings in vanilla paks.

## What's in this repo

| Path | Contents |
|------|----------|
| `game-states/` | Enum catalogs from `ArkAscended.exe` + pak reconstruction (`EPrimalItemType`, `ECheatActorType`, …) |
| `live-data/scripts/` | Crosswalk builders, LLM lookup pack builder, SP save monitor |
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

## Bridge mods (on-disk references)

| Mod | CurseForge | Role |
|-----|------------|------|
| MxCheatUI | 1028139 | Item/creature spawn datatables → blueprint crosswalk |
| GaiaCommands | 936457 | Admin asset search bridge |

## Session reference (The Center SP, 2026-06-11)

Validated in `live-data/bundles/session_20260611_center_combat_destruction_v1.json`:

- Character: CTheRain
- Activity: grapples, element, Tek Rifle structure/dino destruction
- Exit save SHA256 in bundle manifest (full `.ark` stays local on `S:`)

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

## License

Research / assessment artifacts. Game content © Studio Wildcard. Mod extracts © respective authors.
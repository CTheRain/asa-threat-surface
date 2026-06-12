# capsule_000_survival_test

First **ARK Maker State Lab** tray — the goblin in the jar. Proves capsule machinery before bug-specific reproduction.

## Goal

One actor · one template · one Lua logger · one save/reload · one before/after screenshot · one patch-survival check.

| Piece | This capsule |
|-------|----------------|
| **Actor** | `PrimalItem_TekRifle_C` (`EPrimalItemType:Weapon`) |
| **Template** | The Center SP session anchor (local mirror, not in git) |
| **Lua logger** | `logger/survival_v1.lua` (scaffold — ships with ARK Maker DLC) |
| **Save/reload** | Save after giveitem → exit → reload → scan save strings |
| **Screenshots** | `runs/run_*/screenshots/01`–`06` |
| **Patch check** | Re-run tray on new build; update `patch_survival` in manifest |

## Evidence bridge

This capsule is **not** invented from a clip. It cites existing repo proof:

- Session bundle: `live-data/bundles/session_20260611_center_combat_destruction_v1.json`
- Sim scenario: `craft_tek_rifle_sp` in `game-states/asa_game_states_sim.json`
- Lookup entity: `PrimalItem_TekRifle_C` in `asa_game_lookup_quick_v1.json`

## Manual run (pre-DLC)

Until ARK Maker DLC loads capsules automatically:

1. Start monitor: `live-data/scripts/START_MONITOR.ps1`
2. Load SP The Center from `template.local_save_anchor` (copy to live save folder locally)
3. `EnableCheats` → `giveitem` Tek Rifle blueprint (see lookup pack `giveitem` field)
4. Screenshot inventory (**redact HUD names** if publishing)
5. Save and exit
6. Reload save
7. Screenshot again; confirm `PrimalItem_TekRifle_C` in mirrored `.ark` strings
8. Copy artifacts to `runs/run_YYYYMMDD_HHMMSS/`
9. Write `reports/verdict.json` with pass/fail

## State tray (walk order)

```text
clean_control → suspect_setup → trigger_ready → bug_activation
  → first_corrupted → persisted_corrupted → post_patch_verification
```

For this survival test, `bug_activation` and `first_corrupted` document **expected correct** behavior (item persists), not a corruption bug.

## Runs / reports

| Folder | Contents |
|--------|----------|
| `runs/` | Per-run `run_manifest.json`, `logger_output.jsonl`, screenshots |
| `reports/` | `verdict.json`, optional `report_YYYYMMDD.md` for toolkit swarm |

Binary saves **never** go in this folder — only manifests and scrubbed verdicts.

## Pass criteria

From `capsule_manifest.json` → `lua_logger.pass_condition`:

> `PrimalItem_TekRifle_C` present in save strings after reload; `EPrimalItemType:Weapon` hook matches lookup pack.

## Docs

- [`../../docs/ARK_MAKER_STATE_LAB.md`](../../docs/ARK_MAKER_STATE_LAB.md)
- [`../../docs/CAPSULE_SCHEMA.md`](../../docs/CAPSULE_SCHEMA.md)
- [`../../docs/PATCH_DAY_WORKFLOW.md`](../../docs/PATCH_DAY_WORKFLOW.md)
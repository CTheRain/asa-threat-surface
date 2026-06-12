# Capsule Schema

Formal contract for **ARK Maker State Lab** reproduction units. Capsules live under `capsules/` in this repo; binary save artifacts stay local.

---

## Directory layout

```text
capsules/
  capsule_NNN_short_slug/
    capsule_manifest.json    # required — machine contract
    README.md                # required — human runbook
    runs/                    # per-run artifacts (gitignored binaries)
      run_YYYYMMDD_HHMMSS/
        run_manifest.json
        logger_output.jsonl
        screenshots/
    reports/                 # verdict packets for toolkit swarm / dev reports
      report_YYYYMMDD.md
      verdict.json
```

**Never commit:** `.ark`, `.arkbak`, `.arkprofile`, raw screenshots with HUD names (optional policy), or mod archives. See [`SAFETY_BOUNDARY.md`](SAFETY_BOUNDARY.md).

---

## `capsule_manifest.json`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `capsule_id` | string | yes | Stable ID, e.g. `capsule_000_survival_test` |
| `schema_version` | int | yes | Currently `1` |
| `status` | enum | yes | `scaffold` \| `ready` \| `verified` \| `regressed` \| `retired` |
| `title` | string | yes | Short human title |
| `summary` | string | yes | One paragraph: what this tray reproduces |
| `ark_maker_lab` | object | yes | Lab metadata (see below) |
| `evidence_bridge` | object | yes | Links back to threat-surface repo |
| `actor` | object | yes | Primary entity under test (one actor rule for scaffold) |
| `template` | object | yes | World/setup template reference |
| `lua_logger` | object | yes | ARK Maker script contract |
| `state_tray` | object | yes | Seven fossil slots (see below) |
| `patch_survival` | object | yes | Version matrix and pass criteria |
| `tags` | string[] | no | e.g. `craft`, `weapon`, `save-reload` |

### `ark_maker_lab`

```json
{
  "program": "ARK Maker State Lab",
  "phase": "pre-lab | dlc-alpha | dlc-beta",
  "dlc_only": true,
  "net_mode": "Standalone",
  "map": "TheCenter_WP",
  "game_sku": "ASA"
}
```

### `evidence_bridge`

Links capsule to existing repo evidence — **required before status `ready`**.

```json
{
  "threat_surface_refs": [
    "threat-surface/docs/asa_threat_surface_v1.md#client-trust",
    "game-states/asa_creature_item_player.json#EPrimalItemType"
  ],
  "session_bundle": "live-data/bundles/session_20260611_center_combat_destruction_v1.json",
  "lookup_entity": "PrimalItem_TekRifle_C",
  "sim_scenario": "craft_tek_rifle_sp",
  "crosswalk_row": "item_creature_crosswalk_v2.json"
}
```

### `actor`

One primary actor for minimal capsules.

```json
{
  "kind": "item | creature | structure | player_state",
  "class_ref": "PrimalItem_TekRifle_C",
  "display_name": "Tek Rifle",
  "blueprint_ue": "/Game/PrimalEarth/CoreBlueprints/Weapons/PrimalItem_TekRifle.PrimalItem_TekRifle",
  "enum_hooks": ["EPrimalItemType:Weapon"]
}
```

### `template`

Describes the controlled world — not a committed save file.

```json
{
  "type": "minimal_sp | session_anchor | blank_map",
  "map": "TheCenter_WP",
  "description": "Fresh SP character, admin cheats enabled, empty inventory except test item",
  "local_save_anchor": "<local-data>/ARK_LiveData/saves/20260611_215612__TheCenter_WP.ark",
  "committed_to_git": false
}
```

### `lua_logger`

ARK Maker DLC script contract (paths relative to capsule when DLC exists).

```json
{
  "script": "logger/survival_v1.lua",
  "triggers": ["OnCapsuleLoad", "OnSaveBefore", "OnSaveAfter", "OnReloadComplete"],
  "emits": ["class_ref", "enum_hook", "save_size_bytes", "timestamp_utc"],
  "pass_condition": "class_ref present in save strings after reload"
}
```

### `state_tray`

Seven fossil slots. Each slot:

| Subfield | Type | Description |
|----------|------|-------------|
| `label` | string | Human name |
| `description` | string | What should be true at this stage |
| `persistence_layer` | string | `memory` \| `save_ark` \| `arkbak` \| `tribe_log` \| `primal_console` |
| `expected_hooks` | string[] | Enum or synthetic hooks, e.g. `EPrimalItemType:Weapon` |
| `disk_proof` | object | `local_mirror`, `sha256` (optional), `size_bytes` — local only |
| `screenshot` | string | Path under `runs/` when captured |
| `logger_checkpoint` | string | Lua event name that must fire |

**Slots (fixed order):**

| Key | Purpose |
|-----|---------|
| `clean_control` | Known-good baseline before suspect conditions |
| `suspect_setup` | Preconditions placed (inventory, structures, tames) |
| `trigger_ready` | Lua armed; player at trigger position |
| `bug_activation` | Trigger fired; in-memory effect observed |
| `first_corrupted` | First observable wrong state (may equal activation for simple bugs) |
| `persisted_corrupted` | Wrong state survives save boundary |
| `post_patch_verification` | Re-run after game patch; pass/fail recorded |

For **survival tests** (no bug yet), `bug_activation` and `first_corrupted` document **expected correct** behavior.

### `patch_survival`

```json
{
  "baseline_game_build": "ASA-<build>-<date>",
  "checklist": [
    "class_ref still in save after reload",
    "enum_hooks unchanged in lookup pack",
    "sim_scenario steps still valid",
    "logger pass_condition met"
  ],
  "regression_severity": "none | cosmetic | mechanic | security",
  "last_verified_build": null,
  "last_verified_utc": null
}
```

---

## `run_manifest.json` (per run)

Written under `runs/run_*/` when ARK Maker executes a capsule.

```json
{
  "run_id": "run_20260612_143022",
  "capsule_id": "capsule_000_survival_test",
  "started_utc": "2026-06-12T14:30:22Z",
  "finished_utc": "2026-06-12T14:32:01Z",
  "game_build": "ASA-xxx",
  "ark_maker_dlc_version": "0.1.0-scaffold",
  "tray_completed": ["clean_control", "suspect_setup", "trigger_ready"],
  "result": "pass | fail | partial",
  "artifacts": {
    "logger_output": "logger_output.jsonl",
    "screenshots": ["screenshots/before_save.png", "screenshots/after_reload.png"]
  }
}
```

---

## `verdict.json` (toolkit swarm packet)

Distilled output — safe to attach to LLM chats or dev reports.

```json
{
  "capsule_id": "capsule_000_survival_test",
  "verdict": "pass",
  "summary": "Tek Rifle class ref survived save/reload on build ASA-xxx",
  "mechanic_registry_update": null,
  "evidence_citations": [
    "session_20260611_center_combat_destruction_v1",
    "EPrimalItemType:Weapon"
  ],
  "wildcard_framing": "Client-trusted inventory persistence observable on disk; reload did not strip PrimalItem class ref.",
  "video_packet": null
}
```

---

## Status transitions

```text
scaffold  →  ready     (evidence_bridge complete, local anchors exist)
ready     →  verified  (ARK Maker run pass on baseline build)
verified  →  regressed (patch-day fail)
verified  →  retired   (mechanic fixed; tray kept for history)
regressed →  verified  (re-pass after fix or false alarm cleared)
```

---

## Validation (pre-DLC)

Until ARK Maker DLC ships, validate manifests manually:

```powershell
# JSON well-formed
python -c "import json; json.load(open('capsules/capsule_000_survival_test/capsule_manifest.json'))"

# Evidence bridge paths exist in repo
python scripts/validate_capsule_bridge.py   # future script
```

Cross-check enum hooks against `live-data/bundles/asa_game_lookup_quick_v1.json` and sim scenarios in `game-states/asa_game_states_sim.json`.
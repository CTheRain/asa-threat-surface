# Patch Day Workflow

How **ARK Maker State Lab** uses capsules to survive game updates. Official PvP may break silently; the lab re-runs frozen trays and emits verdict packets.

---

## Actors

| Role | Tool |
|------|------|
| Evidence map | `asa-threat-surface` repo (this) |
| Disk monitor | `live-data/scripts/asa_game_state_monitor.py` |
| Capsule tray | `capsules/capsule_NNN_*/` |
| Reproduction | ARK Maker DLC (future) |
| Verdict refinery | toolkit swarm (future) |

---

## Timeline

```text
T0  Game patch drops (Steam)
T1  Refresh static surfaces (optional, local)
T2  Re-run capsule matrix in ARK Maker SP
T3  Compare logger + disk proof vs baseline
T4  Update lookup/crosswalk if class refs shifted
T5  Publish verdict packets (not raw saves)
```

---

## T0 — Patch lands

1. Note new build ID from `ShooterGame.log`, `appmanifest_2399830.acf`, or Steam news.
2. Capture fingerprints and scan patch strings:

```powershell
python scripts/capture_steam_build_snapshot.py
python scripts/scan_patch_surface_strings.py
```

See [`STEAM_PATCH_DIFF.md`](STEAM_PATCH_DIFF.md) for depot manifest GIDs, exe surface diff, and crosswalk joins.
3. Do **not** overwrite baseline mirrors in `<local-data>/ARK_LiveData/saves/` — copy to a dated folder first:

```text
<local-data>/ARK_LiveData/saves/patch_YYYYMMDD/
```

4. Update `patch_survival.baseline_game_build` only when intentionally re-baselining a verified capsule.

---

## T1 — Refresh evidence map (local, optional)

If enums or class refs may have shifted:

```powershell
# Re-run game-state extraction on S: working copy (not in git)
# Then refresh published snapshots if needed:
python live-data/scripts/build_item_creature_crosswalk.py
python live-data/scripts/build_asa_game_lookup_pack.py
python scripts/build_game_states_sim.py
```

Diff focus:

- `game-states/asa_creature_item_player.json` — enum value sets
- `live-data/bundles/item_creature_crosswalk_v2.json` — join breakage
- `threat-surface/asa_threat_surface_index_v1.json` — new cheat/intel strings

Commit **indexes only** — never raw paks or saves.

---

## T2 — Capsule matrix re-run

Run order (smallest → largest):

| Priority | Capsule type | Why first |
|----------|--------------|-----------|
| P0 | `capsule_000_survival_test` | Proves lab machinery + save/reload |
| P1 | Single-actor craft/spawn trays | Class ref persistence |
| P2 | Combat / tribe-log trays | Multi-layer persistence |
| P3 | Suspect-bug trays | Regression signal for known issues |

Per capsule in ARK Maker:

1. Load `capsule_manifest.json`
2. Restore `template.local_save_anchor` from dated patch folder (or clean control slot)
3. Execute `lua_logger` triggers in order
4. Walk `state_tray` slots — capture logger + screenshots
5. Write `runs/run_YYYYMMDD_HHMMSS/run_manifest.json`

---

## T3 — Compare vs baseline

For each `state_tray` slot:

| Check | Pass | Fail signal |
|-------|------|-------------|
| `expected_hooks` still in save strings | hook found | missing enum/class ref |
| `disk_proof.size_bytes` within tolerance | ± expected delta | zero-size or corrupt magic |
| `lua_logger.pass_condition` | logger emits pass | timeout or wrong payload |
| Sim scenario still valid | HTML simulator steps match | orphan hooks in `asa_game_states_sim.json` |

Set `capsule_manifest.status`:

- **verified** — all checklist items pass on new build
- **regressed** — any P0/P1 checklist fail
- **retired** — bug fixed upstream; tray kept as historical proof

---

## T4 — Update repo artifacts

If class refs or hooks changed:

1. Regenerate lookup pack and crosswalk (T1 scripts)
2. Update `evidence_bridge` paths in affected capsules
3. Add `reports/report_YYYYMMDD.md` with human summary
4. Write `reports/verdict.json` for toolkit swarm

Example report header:

```markdown
# Patch report — ASA build YYYYMMDD

## Capsule matrix
| Capsule | Result | Notes |
|---------|--------|-------|
| capsule_000_survival_test | pass | Tek Rifle reload OK |

## Repo updates
- crosswalk v3: 12 class ref path changes
- sim scenario craft_tek_rifle_sp: unchanged
```

---

## T5 — Verdict packets (outbound)

Toolkit swarm receives **only**:

- `reports/verdict.json`
- Cited enum hooks and method-proof framing from `threat-surface/docs/`
- Optional redacted video packet (no tribe names, no server IPs)

**Never outbound:**

- Raw `.ark` / `.arkbak`
- Pegasus-style session lists
- Player/tribe identifiers from Official PvP

Wildcard-facing language template (from threat surface doctrine):

> "After build \<X\>, client-trusted \<persistence layer\> still accepts \<class ref / enum hook\> without server revalidation. Capsule \<id\> reproduces in ARK Maker SP standalone."

---

## Regression matrix (template)

Maintain in each capsule `README.md` or a central `capsules/PATCH_MATRIX.md` when the catalog grows:

| Capsule | Baseline build | Last verified | Last result |
|---------|----------------|---------------|-------------|
| `capsule_000_survival_test` | TBD | — | scaffold |

---

## Emergency: broken save compatibility

If patch invalidates all local anchors:

1. Mark affected capsules `status: scaffold` until new anchors captured
2. Run fresh SP session with monitor (`START_MONITOR.ps1`)
3. Promote new mirror to `template.local_save_anchor`
4. Re-run from `clean_control` only — do not skip trays

See [`ARK_MAKER_STATE_LAB.md`](ARK_MAKER_STATE_LAB.md) for the evidence bridge and [`SAFETY_BOUNDARY.md`](SAFETY_BOUNDARY.md) for red lines.
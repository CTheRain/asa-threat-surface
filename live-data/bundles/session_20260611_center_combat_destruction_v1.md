# Session Bundle — The Center SP Combat / Destruction

**Bundle ID:** `session_20260611_center_combat_destruction_v1`  
**Date:** 2026-06-11 (local)  
**Map:** The Center (`TheCenter_WP`)  
**Mode:** Singleplayer  
**Character:** CTheRain (tribe: Slaanesh / Wow All Horizontal)

## Activity

Rep craft (grapples, element, Tek Rifle) followed by sustained Tek Rifle destruction of structures and wild/tamed dinos. Wall-clock session window: **21:56:11 → 22:12:07**.

## Persistence snapshot (live disk at close)

| Layer | End state | Notes |
|-------|-----------|-------|
| **Main** `TheCenter_WP.ark` | **14,204,928 B** @ 22:12:07 | +1,335,296 B from session-open baseline (12,869,632 B) |
| **Rolling `.arkbak`** | **20 slots** (`_0000`–`_0019`) | User deleted one slot when hitting cap; `_0002`–`_0019` created this session |
| **AntiCorruption** `.bak` | **12,869,632 B** @ 21:56:10 | Did **not** track late destruction |
| **Profile** `PlayerLocalData.arkprofile` | **2,404,339 B** @ 22:12:06 | Brief mid-session spike to ~2,417,661 B |

## Key mirrored anchors (`<local-data>/ARK_LiveData\saves\`)

| Role | Mirror | Size |
|------|--------|------|
| Session open | `20260611_215612__TheCenter_WP.ark` | 12,869,632 B |
| Pre-destruction | `20260611_220144__TheCenter_WP.ark` | 12,910,592 B |
| Post-combat (first arkbak window) | `20260611_220417__TheCenter_WP.ark` | 12,935,168 B |
| Late destruction peak | `20260611_221108__TheCenter_WP.ark` | 14,221,312 B |
| **Exit (final)** | `20260611_221210__TheCenter_WP.ark` | **14,204,928 B** |

**Exit hashes**

- Main: `331EDFAE51E1473B1CA1C850278094C33DB81F386510BAA99941FADF256705AB`
- Profile: `48BF855F936BE4D4E88D69850E42A833AC5E0E7B7D8201070A9F42B3DA840970`

**Mirrored session arkbak:** `_0002`–`_0019` (21 mirror files including superseded `_0016` at `221029` and replacement at `221152`).

## Combat / craft evidence in saves

**Binary class refs (final main):** `PrimalItemAmmo_GrapplingHook`, `PrimalItem_TekRifle`, Element resources, `PrimalItem_DinoSpawner_Zeppelin`, Tek/Thatch structure blueprints.

**Tribe log delta (open → exit):** 283 → 1,113 entries (+830 instances, 175 unique new event types). Session-added destroy/kill samples include:

- Structures: BattleRig (multiple), Tek Generator, Tek Trough, Thatch Ceiling, Locomotive, Motorboat, Hover Skiff, Tek Transmitter
- Dinos: Armadoggo, Zomdodo (in extended log), Troodon, many Lvl 1 test kills
- Attribution: `killed by CTheRain - Lvl 195`, `Your Tribe killed …`

Full extracts are in the JSON manifest under `tribe_log_delta_open_to_exit`.

## Monitor assessment

| Aspect | Result |
|--------|--------|
| **Verdict** | Usable for **save-trust / rollback** analysis with known gaps |
| **Coverage** | Main `.ark`, rolling `.arkbak`, profile, configs under `SavedArksLocal` + `LocalProfiles` |
| **Events** | 504 total; 92 The Center; 33 main mirrors; 23 arkbak mirrors |
| **Crash #1** | ~22:08 — `FileNotFoundError` on transient `TheCenter_WP.ark-journal` during atomic save |
| **Fix** | `asa_game_state_monitor.py`: skip `*-journal`/temp; ignore `FileNotFoundError` on poll |
| **Crash #2** | First monitor run ~17 min, exit 1 (pre-fix); restarted successfully through exit |
| **Monitor** | PID 8904 stopped after game close |

### Gaps

- No live projectile/combat lines — `ShooterGame.log` stale (last write May 2024)
- `ItemLog` not refreshed during SP session
- AntiCorruption backup not polled on same cadence as rolling backups
- High churn → many duplicate main mirrors (by design)
- Disk-only — no in-memory GameState / replication capture

## Threat-surface tie-in

Three persistence layers (main, 20-slot rolling arkbak, lagging anticorr) are directly relevant to **save-trust and rollback abuse** framing. Combat outcomes and destroy events are **client-trusted** and written into the world blob/tribe log without server validation in SP — matching the project doctrine (client-trusted paths, not cheat-brand strings in vanilla paks).

## Artifacts

- **Manifest:** `<local-data>/ARK_LiveData\bundles\session_20260611_center_combat_destruction_v1.json`
- **Monitor script:** `<local-data>/ARK_LiveData\scripts\asa_game_state_monitor.py`
- **Live feed:** `<local-data>/ARK_LiveData\live_events.jsonl`
- **Related:** `<local-data>/ARK_ThreatSurface\`, `<local-data>/ARK_GameStates\`
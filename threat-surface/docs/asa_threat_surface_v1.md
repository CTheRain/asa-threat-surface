# ASA Threat Surface v1

Generated: 2026-06-11  
Output root: `S:\ARK_ThreatSurface\`  
Method: read-only local scans of `ArkAscended.exe`, IoStore `.utoc` files, `ShooterGame\Saved\`, and your existing CSV/evidence imports.

---

## 1. Not in the CVAR dump

Your file [`asa_console_command_descriptions_v0_full.md`](C:\Users\SLAANESH\Downloads\asa_console_command_descriptions_v0_full.md) lists **6,272 dot-style engine CVARs** (`r.*`, `p.*`, `net.*`, `ark.*`, etc.). That scan method **cannot** surface:

### Third-party cheat client brands
**GPT, Aurora, King** — no embedded brand strings found in vanilla ASA exe/pak scans. These are external paid injection/overlay products; they hook client trust at runtime rather than shipping inside Wildcard's files.

### External intel bot (Pegasus)
Pegasus is a **Discord bot**, not a console command. Your evidence file defines its surface:

| Command | What it does |
|---|---|
| `/server` | Scan server for online players + tribe/platform |
| `/scanserver` | Auto-scan with live updating player list |
| `/trackplayer` | Track by EOS ID, Steam ID, or implant ID |
| `/serverplayerhistory` | Historical joins per server |
| `/markplayersonserver` | Bulk-mark online players to enemy/friend lists |
| `/addplayer`, `/mylist`, comments | Persistent player profiling |

Source: `S:\ARK_ThreatSurface\asa_intel_surfaces_v1.csv` (12 `pegasus_command` rows imported from your evidence pack).

### Real cheat verbs your CVAR dump missed
These live as plain strings in `ArkAscended.exe`, not as `something.something` CVARs:

| Verb / entry | Source |
|---|---|
| `cheat fly` | exe string |
| `cheat ce stoptime 1 1` | exe string |
| `cheat giveitemnum`, `cheat spi`, `cheat tod` | exe string |
| `EnableCheats`, `ShowCheatMenu` | your `PrimalConsole.ini` history |
| `ToggleTracker`, `ark.PlayerHeatMapDebugDraw` | your `PrimalConsole.ini` history |

Full list: `S:\ARK_ThreatSurface\asa_cheat_commands_v1.csv` (248 rows).

### Why the 6,272-command MD misleads for this task
It is excellent for engine tuning research. It is **the wrong index** for "what do cheat clients and watcher bots abuse" because:
- Admin cheat verbs use a `cheat <verb>` pattern
- Pegasus uses Discord slash commands
- Injection cheats abuse **classes and RPC paths** (`UShooterCheatManager`, movement validation), not CVAR names

---

## 2. In-game cheat abuse systems

What King / Aurora / GPT-class tools appear to target in ASA (from vanilla surfaces, not client binaries):

### A) Movement and physics trust
High-value CVARs and strings tied to client-authoritative movement:

| Surface | Relevance |
|---|---|
| `ark.AutonomousCorrectionThreshold` | How far client movement can self-correct |
| `ark.EnableServerMovementCorrections` | Server position error checking toggle |
| `p.NetlimitExploitFixTriggerTime` | Netlimit exploit fix timing |
| `np2.CMC.EnableClientAuthScheduledPushForces` | Client auth scheduled push forces |
| `p.ClientMoveCombineDelta` | Client move combining |
| `ServerExceedsAllowablePositionError` | Allowable position error gate |

Source: `asa_cheat_commands_v1.csv` (`high_value_cvar` rows) + exe strings.

### B) Built-in cheat manager (hook target)
`UShooterCheatManager` and `ServerCheatManager` symbols in exe, including:
- `AttackAOE`, `QueueAttackAOE`
- `cheat fly`, `cheat spi %s %f 0`
- `CHEAT FAILURE: Must have proper permissions and a valid player character.`

Third-party cheats do not replace this system — they bypass server validation or inject around it.

### C) Combat / projectile validation (your compound bow notes)
Pak index found thousands of combat-related asset names in utoc strings. Exe carries shooter combat classes but **hit-registration logic** lives primarily in blueprints under paks — our v1 index names them but does not decompile logic.

**Wildcard-facing wording:** "Players appear to land projectile hits without valid aim alignment; investigate server-side validation of projectile direction and hit registration."

### D) Anti-cheat boundary
EOS / BattlEye strings found in exe scan:
- `Anti-Cheat requested session %s in %s must match current session %s!`
- `Disconnected from server due to Anti-Cheat error`
- `errors.com.redpoint.eos.anticheat.*` CVAR family

Injection cheats interact with this boundary; Pegasus-style bots often **avoid** it by staying external to the game process.

### E) Legit cheat menu assets (not third-party brands)
Phase 1 utoc index + Phase 2b retoc extract confirmed vanilla assets:
- `CheatMenu.uasset`, `CheatMenuButton.uasset`, `CheatMenuCheatButton.uasset`
- `CheatMapJumpButton.uasset`, `CheatMenuOptionTypes.uasset`
- `ClientExplodingProjectile.uasset` (combat validation surface)

**Extracted to disk:** `S:\ARK_ThreatSurface\extracted\cheatmenu_focus\` (15 files, manifest in `manifests\cheatmenu_extract_manifest_v1.json`).

These are shipped debug/admin UI — not King/Aurora/GPT products.

### F) Phase 2b ucas meat scan (deeper than utoc index)
Full mirrored `.ucas` string scan (`pak_meat_strings_v1.csv`):

| Ucas file | Keyword hits |
|---|--:|
| `pakchunk0-Windows.ucas` | 77,042 |
| `pakchunk2-Windows.ucas` | 8,421 |
| `pakchunk9-Windows.ucas` | 7,317 |
| `pakchunk8-Windows.ucas` | 6,788 |
| `global.ucas` | 1,098 |
| **Total unique strings** | **113,382** |

Top categories (first-match): `Primal` (47k), `EOS` (21k — includes Astraeos false positives), `Hit` (21k), `Shooter` (12k), `Weapon` (6k), `Projectile` (625), `Cheat` (82), `Tracking` (38).

**Still absent:** GPT / Aurora / King brand strings in any ucas pass.

---

## 3. Intel bot abuse systems

What Pegasus-class watcher bots need from the game/ecosystem:

### A) Session and player list exposure
Exe/pak strings include session machinery:
- `ListSessions`, `DumpOnlineSessionState`
- `FOnlineSessionInterfaceEOS`
- `UUI_ListSessions::OnGameModeComboBoxSelectionChanged`

If official/session browser layers expose player lists with tribe + platform context, external bots can automate what a human would scout manually.

### B) Identity correlation
Surfaces matching Pegasus `/trackplayer` inputs:
- `GetPlayerStateFromUniqueNetId`
- `FindPlayerStateFromHashedUniqueID`
- `steam.id`, `steam.sessionTicket` CVAR/help strings
- Implant-related strings (imported via intel pattern pass)

**Sanity note:** Finding `PlayerStateOwnsDarkPegasus` in intel CSV is the **DLC cosmetic**, not the Discord bot.

### C) Actor tracking keys (in-game ESP-adjacent machinery)
Strong cluster in `asa_intel_surfaces_v1.csv`:
- `ActorTracking_TempTrack_TrackState_Players`
- `ActorTracking_TempTrackPOIVisibleState_Players`
- `CustomActorTracking_MaxAllowedWaypointTrackedActors`
- Debug toggles: `ToggleTracker`, `ark.PlayerHeatMapDebugDraw` (from your console history)

External bots mirror this at network/session scope; in-game cheats mirror it at render/RPC scope.

### D) Saved-folder entry points (556 files inventoried)
Not pak-exe, but relevant to "weird JSON/template entry points":

| Extension | Count | Notes |
|---|---:|---|
| `.pnt` | 276 | Paint/template blobs |
| `.ini` | 119 | Includes `DinoExports\` |
| `.formertribeownerlog` | 87 | Tribe ownership history logs |
| `.template` | 55 | Structure templates (binary) |
| `.arkprofile` | 3 | Player profile blobs |

Manifest: `S:\ARK_ThreatSurface\saved_entrypoints_manifest_v1.json`  
Each entry has `sha1`, `magic_hex`, and `printable_preview` for manual inspection.

---

## 4. Wildcard-facing fix framing

Use method-proof language aligned with your ARK Maker Lab doctrine — **not** a raid manual.

### For injection cheats (King / Aurora / GPT-class)
> "Official PvP appears vulnerable to client-trusted movement and projectile hit reporting. Server-side validation should treat aim direction, projectile travel time, and position corrections as authoritative — not cosmetic."

Concrete systems to name in reports:
- Movement correction thresholds (`ark.AutonomousCorrectionThreshold`, netlimit fix CVARs)
- Projectile hit registration (compound bow / silent-aim class of reports)
- EOS anti-cheat session integrity checks already present but bypassed by non-injected techniques

### For intel bots (Pegasus-class)
> "Official PvP has a third-party intel problem. Outside services can correlate EOS/Steam/implant identifiers with live session player lists and historical join data. Do not just ban one bot — reduce the data exposure that makes large-scale tracking possible."

Concrete policy asks:
- Minimize player-identifying fields in session browser / server list responses
- Rate-limit or gate automated session queries
- Reduce cross-server join history retrievability by unauthenticated third parties
- Audit what BattleMetrics-style public data + game session data combined can reconstruct

### What you can prove locally without Official access
| Claim | Evidence file |
|---|---|
| Vanilla game ships cheat verbs + cheat manager | `asa_cheat_commands_v1.csv` |
| Vanilla game ships actor tracking + session classes | `asa_intel_surfaces_v1.csv` |
| Vanilla paks name CheatMenu + combat assets | `pak_high_value_strings_v1.csv` |
| Full ucas keyword surface scanned (258 GB mirror) | `pak_meat_strings_v1.csv` |
| CheatMenu + ClientExplodingProjectile on disk | `extracted\cheatmenu_focus\` |
| 254k asset paths indexed via retoc | `indexes\retoc_list_cache_v1.json` |
| Pegasus command surface exists externally | Pegasus rows in `asa_intel_surfaces_v1.csv` |
| Third-party cheat brands not in game files | absence in exe/utoc/ucas scans |

### Red lines (do not cross)
- Do not build Pegasus-like tracking automation
- Do not publish raid routing from live intel
- Do not claim GPT/Aurora/King inner workings without captured client binaries (not present in this scan)

---

## Scan summary

| Metric | Value |
|---|---:|
| Cheat/intel exe records | 248 cheat + 441 intel |
| Pegasus commands imported | 12 |
| Console history commands | 50 |
| Saved entrypoints | 556 |
| Pak utoc keyword strings (Phase 2) | 8,592 |
| IoStore mirror (Phase 2b) | 26 files / 258.36 GB |
| Ucas meat keyword strings (Phase 2b) | 113,382 |
| Retoc asset paths indexed | 254,737 |
| Targeted assets extracted | 434 broad + 15 CheatMenu focus |
| High-value CVARs tagged | 21 |

**Machine index:** `S:\ARK_ThreatSurface\asa_threat_surface_index_v1.json` (Phase 1 + 2b merged)  
**Sanity guide:** `S:\ARK_ThreatSurface\HOW_IT_WORKS.md`  
**Re-run scripts:** `S:\ARK_ThreatSurface\scripts\`
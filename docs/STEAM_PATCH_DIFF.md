# Steam Patch Diff Pipeline

Cross-reference **Steam build commits** to **game file changes** and **possible state surfaces** — without relying on SteamDB scraping.

---

## Short answer

**Yes, it is possible** — but the reliable path is **local Steam client metadata + your threat-surface indexes**, not a SteamDB API.

| Source | What you get | Automatable? |
|--------|----------------|--------------|
| **SteamDB** (web) | Human-readable depot history, patch note pages | No official API; do not scrape |
| **`appmanifest_2399830.acf`** | `buildid`, per-depot `manifest` GID, bytes downloaded | Yes — local file |
| **`Steam/depotcache/*.manifest`** | Cached depot manifests (file list + content hashes) | Yes — diff two GIDs |
| **Key file SHA256** | `ArkAscended.exe`, `global.ucas`, `pakchunk0-*` | Yes |
| **Exe string scan** | New INI keys, enum names, BP strings | Yes — map to `game-states/` |
| **Crosswalk / lookup** | Class refs for items/creatures in patch notes | Yes — `item_creature_crosswalk_v2` |
| **Capsules** | Behavioral regression after patch | Yes — ARK Maker State Lab |

```text
Steam build commit (buildid + manifest GID)
  → depot manifest diff (which files changed)
  → exe / pak fingerprint diff
  → new strings → enum / INI / blueprint surfaces
  → crosswalk + sim scenarios + capsule matrix
```

---

## v88.22 on this machine (2026-06-11)

From local `appmanifest_2399830.acf`:

| Field | Value |
|-------|--------|
| **buildid** | `23687127` |
| **Main depot** | `2399831` |
| **New manifest GID** | `2778173512205025784` |
| **Previous manifest GID** (depotcache) | `4801118673125721466` |
| **Bytes downloaded** | ~14.6 MB |

Patch notes mention: Queen Bee hives, Planning Structure decay, Cryofridge/Vault structure limits, Classic dino stacking detection, crash fix.

### Exe surface scan (new vs published catalog)

Strings **found in current `ArkAscended.exe`** but **not** in published `game-states/asa_game_states.csv`:

| Keyword | Encoding | Likely surface |
|---------|----------|----------------|
| `DinoStacking*` / `EnableDinoStackingDetection` | UTF-16LE | Server INI / Classic anti-stack |
| `PreventPlannedStructureDecayReset` | UTF-16LE | `GameUserSettings.ini` server option |
| `PlanningStructure` / `PlannedStructure` | ASCII | Structure decay / build-guide BP |
| `NearbyStructure` / `StructureLimit` | ASCII | Structure cap logic |
| `CryoFridge` | UTF-16LE | `PrimalItemStructure_CryoFridge_C` (already in crosswalk) |

**Crosswalk already has:** `PrimalItemStructure_CryoFridge_C`, `PrimalItemSkin_ChibiDino_QueenBee_C`.

**Gap:** publish a fresh exe enum extract after each patch, then diff against the prior `game-states` snapshot.

---

## Workflow (patch day + file diff)

### 1. Capture build snapshot (before and after update)

```powershell
python scripts/capture_steam_build_snapshot.py
```

Writes `patches/build_snapshots/build_<buildid>.json`:

- Steam `buildid` and depot manifest GIDs
- All cached `depotcache/2399831_*.manifest` entries
- SHA256 of `ArkAscended.exe`, `global.ucas`, `pakchunk0-*`, etc.

**Tip:** run once *before* updating Steam if you know a patch is coming; after update you get two snapshots to diff.

### 2. Diff depot manifests (local depotcache)

Steam keeps prior manifests on disk:

```text
C:\Program Files (x86)\Steam\depotcache\
  2399831_4801118673125721466.manifest   # older
  2399831_2778173512205025784.manifest   # v88.22
```

Same file **paths** appear in both (174 `ShooterGame` entries); **content SHA entries** inside the manifest change. A full parser (SteamKit / DepotDownloader manifest format) gives exact changed files. Until then, use **key file fingerprints** from step 1.

Likely touched for minor patches:

- `ArkAscended.exe` (logic / strings)
- `global.ucas` / `global.utoc` (small global chunk)
- Sometimes `pakchunk0-Windows.ucas` segments (large)

### 3. Scan patch-note keywords in exe

```powershell
python scripts/scan_patch_surface_strings.py
```

Output: `patches/surface_scans/patch_surface_YYYYMMDD.json`

- Which keywords appear in exe (ASCII + UTF-16LE)
- Whether they exist in published `asa_game_states.csv`
- Matching `class_ref` rows from crosswalk

### 4. Map to game states and capsules

| Patch topic | Repo join | Capsule idea |
|-------------|-----------|--------------|
| Cryofridge/Vault structure limit | `PrimalItemStructure_CryoFridge_C`, structure enums | `capsule_NNN_structure_limit` |
| Planning Structure decay | New `PlannedStructure` strings | `capsule_NNN_planning_decay` |
| Dino stacking (Classic) | `EActorListsBP:AL_TAMED_DINOS`, `ECheatActorType:Tame` | `capsule_NNN_dino_stack` |
| Queen Bee hives | Queen / hive BP paths in pak index | `capsule_NNN_queen_hive_overlap` |

Update [`PATCH_DAY_WORKFLOW.md`](PATCH_DAY_WORKFLOW.md) T1: refresh `game-states/` when `new_surface_candidates` is non-empty.

---

## SteamDB vs official Steam

**SteamDB** is useful as a **human bookmark** (depot manifest list, patch note mirror). It does **not** offer a supported API for automation.

Use instead:

1. Local `appmanifest_*.acf` (buildid + manifest GID)
2. Local `depotcache` (manifest binaries)
3. [Steam Web API](https://partner.steamgames.com/doc/webapi) `ISteamNews/GetNewsForApp` for announcement text (no per-file diff)
4. Your own `patches/build_snapshots/` history in this repo (small JSON only)

---

## Repo layout

```text
patches/
  build_snapshots/
    build_23687127.json      # fingerprint after capture script
  surface_scans/
    patch_surface_20260611.json
```

Never commit `.manifest` binaries or full pak mirrors — only JSON fingerprints and scan reports.

---

## Integration with ARK Maker State Lab

```text
Steam patch
  → build snapshot + surface scan (this doc)
  → refresh game-states / crosswalk if needed
  → re-run capsule matrix (PATCH_DAY_WORKFLOW)
  → verdict.json for toolkit swarm
```

The Steam layer answers **what files changed**; capsules answer **what behavior changed**.
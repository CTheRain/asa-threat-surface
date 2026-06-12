# How This Threat Surface Scan Works (Sanity Check Guide)

All outputs live on `S:\ARK_ThreatSurface\`. Game install files are **read only** — nothing in `ARK Survival Ascended` is modified.

## What we are NOT doing

- We are **not** running GPT, Aurora, King, or Pegasus
- We are **not** modifying or deleting anything in the Steam install
- We are **not** decompressing all 258 GB of mirrored IoStore — only targeted `retoc get` on named assets

## Phase 1 — `scan_asa_cheat_intel_surfaces.py`

### Inputs
| Input | What it is |
|---|---|
| `ArkAscended.exe` (~247 MB) | Shipped game binary |
| `asa_console_command_descriptions_v0.csv` | Your prior CVAR dump (engine tuning) |
| `asa_exe_game_state_focused_strings.csv` | Prior focused string scan |
| `PrimalConsole.ini` | Your local console command history |
| `07_Pegasus_Command_List_...txt` | Your Pegasus evidence summary |
| `ShooterGame\Saved\**` | Templates, profiles, dino exports, etc. |

### Method
1. Read the exe in 8 MB chunks (low RAM)
2. Extract printable **ASCII** and **UTF-16LE** strings (same technique as your earlier scans)
3. Match against pattern lists:
   - **Cheat:** `cheat fly`, `UShooterCheatManager`, `EnableCheats`, movement validation strings, etc.
   - **Intel:** `ActorTracking_*`, `ListSessions`, EOS/Steam identity strings, etc.
4. Import Pegasus Discord commands from your evidence file (external bot — not in exe)
5. Pull high-value CVAR rows from your existing CSV (movement, anti-cheat, heatmap debug)
6. Walk `Saved\` and hash/probe `.template`, `.arkprofile`, `.pnt`, etc.

### Outputs
- `asa_cheat_commands_v1.csv` — 248 rows
- `asa_intel_surfaces_v1.csv` — 441 rows
- `saved_entrypoints_manifest_v1.json` — 556 files inventoried
- `asa_threat_surface_index_v1.json` — merged machine index

### How to sanity-check Phase 1 yourself
```powershell
# Re-run (takes ~1 minute)
python S:\ARK_ThreatSurface\scripts\scan_asa_cheat_intel_surfaces.py

# Find real admin cheat verbs embedded in exe
Select-String -Path S:\ARK_ThreatSurface\asa_cheat_commands_v1.csv -Pattern '^exe_string,cheat_verb,cheat '

# Confirm Pegasus commands imported
Select-String -Path S:\ARK_ThreatSurface\asa_intel_surfaces_v1.csv -Pattern 'pegasus_command'

# Confirm cheat client BRAND names are absent from exe scan
Select-String -Path S:\ARK_ThreatSurface\asa_*.csv -Pattern 'Aurora|King cheat|GPT cheat' 
# (should be empty — only DarkPegasus DLC string and Pegasus evidence file paths may appear)
```

## Phase 2 — `index_asa_paks.py`

### Why plain `/Game/` path parsing failed first
UE5 **IoStore** `.utoc` files store compressed chunk tables. Asset paths are often **not** stored as readable `/Game/...` text in the utoc blob (our first parser found 0 paths). That is expected.

### v1 method (PC-safe)
1. Read each `.utoc` file (~115 MB total across 13 files) in 16 MB chunks
2. Extract printable ASCII runs (6–200 chars)
3. Keep strings matching high-value keywords: `Cheat`, `Session`, `PlayerState`, `Weapon`, `EOS`, etc.
4. Also fully string-scan tiny `global.ucas` (3.7 MB only)

### What this gives you
- **8,592 unique keyword hits** from utoc + global.ucas
- Examples found: `CheatMenu.uasset`, `CheatMapJumpButton.uasset`, session-related symbols
- This is an **index of names**, not opened blueprint logic

### What this does NOT give you yet
- Decompressed blueprint properties
- Full asset tree like FModel GUI
- Per-chunk byte extraction from 154 GB `pakchunk0-Windows.ucas`

### If you want deeper pak reading later (optional, heavier)
| Tool | Role | PC cost |
|---|---|---|
| **FModel** | GUI browse/decompress ASA IoStore | Moderate RAM; no full-disk scan |
| **retoc / repak** | CLI list/extract named assets | Targeted extraction only |
| **Our v1 script** | Fast keyword index across utoc | ~2 seconds, ~115 MB read |

Recommendation: stay on v1 index unless you need one specific blueprint. Then use FModel on that path only.

## Phase 2b — Full mirror + ucas meat scan + retoc extract (completed)

All heavy storage on **S:** only. Source paks on C: are read-only.

### Step 1 — `mirror_paks_to_s.py`
| Item | Value |
|---|---|
| Files | 26 `.ucas` / `.utoc` |
| Size | 258.36 GB |
| Dest | `paks_mirror\` |
| Safety | Resume-safe copy + SHA1 verify per file |

### Step 2 — `scan_ucas_meat_strings.py`
| Item | Value |
|---|---|
| Method | Chunked 32 MB read of every mirrored `.ucas` |
| Output | `pak_meat_strings_v1.csv` |
| Unique strings | **113,382** keyword hits |
| Largest file | `pakchunk0-Windows.ucas` → **77,042** hits |
| Safety | Checkpoint after each file; progress in `manifests\ucas_meat_scan_progress_v1.json` |

### Step 3 — `extract_high_value_assets.py` + `extract_cheatmenu_focus.py`
| Item | Value |
|---|---|
| Tool | `tools\retoc\retoc.exe` v0.1.5 |
| List cache | `indexes\retoc_list_cache_v1.json` — **254,737** asset paths across 13 chunks |
| Broad extract | 434 assets (200 cap per priority) → `extracted\` |
| CheatMenu focus | **15/15** assets → `extracted\cheatmenu_focus\` |

CheatMenu focus pulled the full `PrimalEarth/UI/CheatMenu/*` set plus `ClientExplodingProjectile`.

### How to sanity-check Phase 2b yourself
```powershell
# Mirror manifest — should show 26 copied, 0 failed
python -c "import json; print(json.load(open(r'S:\ARK_ThreatSurface\manifests\paks_mirror_manifest_v1.json'))['summary'])"

# Meat scan row count
python -c "print(sum(1 for _ in open(r'S:\ARK_ThreatSurface\pak_meat_strings_v1.csv',encoding='utf-8'))-1)"

# CheatMenu assets on disk
Get-ChildItem S:\ARK_ThreatSurface\extracted\cheatmenu_focus -Recurse -File | Select-Object Name

# Re-merge index after future scans
python S:\ARK_ThreatSurface\scripts\merge_phase2b_index.py
```

### How to sanity-check Phase 2 yourself
```powershell
python S:\ARK_ThreatSurface\scripts\index_asa_paks.py

# Should finish in seconds, not hours
# Check summary in pak_asset_index_v1.json
python -c "import json; print(json.load(open(r'S:\ARK_ThreatSurface\pak_asset_index_v1.json'))['summary'])"
```

## File map on S:

```text
S:\ARK_ThreatSurface\
  scripts\
    scan_asa_cheat_intel_surfaces.py
    index_asa_paks.py
    mirror_paks_to_s.py
    scan_ucas_meat_strings.py
    extract_high_value_assets.py
    extract_cheatmenu_focus.py
    merge_phase2b_index.py
  paks_mirror\              (258 GB IoStore copy)
  extracted\
    cheatmenu_focus\        (15 targeted assets)
  tools\retoc\retoc.exe
  manifests\                (mirror, meat, extract progress)
  indexes\retoc_list_cache_v1.json
  pak_meat_strings_v1.csv   (113k+ ucas keyword hits)
  HOW_IT_WORKS.md
  asa_threat_surface_v1.md
  asa_threat_surface_index_v1.json
```

## Interpreting results

| Finding | Meaning |
|---|---|
| `cheat fly` in exe | Vanilla admin cheat verb shipped with game — not a third-party client |
| `UShooterCheatManager` | Built-in cheat manager class — injection cheats try to hook around this |
| `ActorTracking_*` | In-game tracking state machinery — relevant to ESP/watcher-style intel |
| Pegasus `/trackplayer` in CSV | External Discord bot command — imported from your evidence, not exe |
| `CheatMenu.uasset` in pak index | Legit debug/admin UI assets — different from King/Aurora/GPT brands |
| No `GPT`/`Aurora`/`King` strings | Third-party cheat **brand names** are not embedded in vanilla ASA files |
# Singleplayer memory reader (read-only)

Optional **local-only** tooling under `live-data/scripts/` for numeric vitals and position from `ArkAscended.exe`. This is **not** committed output — only the scripts and offset **template** live in git.

## Hard requirements

| Requirement | Why |
|-------------|-----|
| **Singleplayer only** | Gate refuses dedicated server processes, remote join log lines, and missing `SavedArksLocal` activity |
| **BattlEye disabled** | Launch with `-NoBattlEye`; gate checks log/cmdline and blocks if `BEService.exe` / BattlEye init is active |
| **Read-only** | Uses `pymem` read APIs only — never writes game memory |
| **No secrets in git** | Tokens, `.env`, filled `memory_offsets.json`, `memory_digest.json`, and streams stay local (`.gitignore`) |
| **No player identifiers in output** | Digest emits coordinates and vitals only — no character names, tribe names, or server IPs |

**Do not** use on official servers, player-hosted sessions, or any BattlEye-protected context.

Community rules and liability: [`COMMUNITY_USE_POLICY.md`](COMMUNITY_USE_POLICY.md) (includes **no usage tracking**).

## Community safety (public repo)

This repo is public. **Test on your own SP session first** before sharing with others.

| Step | Command |
|------|---------|
| 1. Offline checks (no game) | `./live-data/scripts/START_PREFLIGHT.ps1` |
| 2. Launch ASA | Singleplayer tray, **`-NoBattlEye`**, close other BattlEye games |
| 3. Memory reader | `./live-data/scripts/START_MEMORY_READER.ps1` — type `SP-ONLY` to confirm |
| 4. Network audit (first run) | `./live-data/scripts/START_NETWORK_AUDIT.ps1` — `research_tool_has_network` must stay `false` |

**Hard blocks built in:**

- Gate refuses dedicated server process, remote-join log lines, active BattlEye, and `BEService.exe` (even if ASA has `-NoBattlEye`)
- `--relaxed-gate` is **dev-only** — requires `ASA_UNSAFE_RELAXED_GATE=1`
- Scripts are AST-scanned for network imports and memory writes in preflight

**If someone ignores the rules and runs on official MP with BattlEye on, they can get banned — that is on them.** The tooling is designed to refuse that context.

### Tamper resistance (honest limits)

Public Python **cannot be DRM**. Anyone determined can edit local files. We still:

| Control | What it does |
|---------|----------------|
| `script_integrity_manifest.json` | SHA256 of each research script; preflight fails if modified |
| `START_*.ps1` launchers | Run preflight + `SP-ONLY` ack before live attach |
| No `--relaxed-gate` | Gate bypass flag removed from community scripts |
| AST preflight | Blocks network imports and pymem write calls |

**For Discord:** point users at **GitHub Releases** (pinned tag), not random forks. Maintainers regenerate manifest after changes:

```powershell
python live-data/scripts/asa_script_integrity.py --write
```

Tell the community: if integrity fails, re-clone — do not hand-edit memory scripts.

## Setup

```powershell
# Optional local mirror (recommended — same as disk monitor)
$env:ARK_LIVE_DATA = "<local-data>\ARK_LiveData"

# Optional if ASA is not in default Steam path
$env:ARK_ASA_SAVED = "C:\...\ARK Survival Ascended\ShooterGame\Saved"

pip install -r live-data/requirements-memory.txt

# First run copies template → local config (gitignored)
./live-data/scripts/START_MEMORY_READER.ps1
```

Fill `memory_offsets.json` per patch using the **offset mapper** (recommended) or Cheat Engine / Dumper-7 on **your** SP tray. Template: `live-data/templates/memory_offsets.template.json`.

### Offset mapper (recommended)

Interactive read-only scans — no Cheat Engine GUI:

```powershell
$env:ARK_LIVE_DATA = "<local-data>\ARK_LiveData"
./live-data/scripts/START_OFFSET_MAPPER.ps1 guide

# With game running in SP (-NoBattlEye):
./live-data/scripts/START_OFFSET_MAPPER.ps1 scan health --value 100
# change health in-game
./live-data/scripts/START_OFFSET_MAPPER.ps1 rescan health --value 73
./live-data/scripts/START_OFFSET_MAPPER.ps1 pointers health
./live-data/scripts/START_OFFSET_MAPPER.ps1 pick health
./live-data/scripts/START_OFFSET_MAPPER.ps1 export --build ASA_YYYYMMDD
```

State: `config/offset_scan_state.json` (gitignored). Export: `config/memory_offsets.json`.

## Outputs (local only)

| File | Contents |
|------|----------|
| `memory_digest.json` | Latest numeric snapshot + gate status |
| `memory_stream.jsonl` | Append-only history for LLM/automation on your machine |

Pair with `asa_game_state_monitor.py` for disk-side evidence; memory layer adds live vitals when offsets are known.

## Network audit (optional)

Verify research tooling is not opening sockets:

```powershell
./live-data/scripts/START_NETWORK_AUDIT.ps1
```

Writes `network_audit_latest.json` locally. **`research_tool_has_network` should stay `false`** for `asa_memory_reader.py` / `asa_game_state_monitor.py`. The game itself may still talk to Steam/EOS in SP — that is separate from our scripts.

## Safety boundary

See [`SAFETY_BOUNDARY.md`](SAFETY_BOUNDARY.md). Memory reads are allowed **only** under the SP + no-BattlEye rules above. Multiplayer tracking, raid intel, and anti-cheat evasion are out of scope.
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

Fill `memory_offsets.json` per patch (Cheat Engine / Dumper-7 on **your** SP tray). Template: `live-data/templates/memory_offsets.template.json`.

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
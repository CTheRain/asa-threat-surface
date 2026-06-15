# ASA singleplayer memory reader (read-only).
# Requirements: SP session, BattlEye DISABLED (-NoBattlEye), offsets filled locally.
# Optional: $env:ARK_LIVE_DATA = "<local-data>\ARK_LiveData"
# Optional: $env:ARK_ASA_SAVED = "...\ShooterGame\Saved"

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "asa_memory_reader.py"
$preflight = Join-Path $PSScriptRoot "asa_safety_preflight.py"
$req = Join-Path (Split-Path $PSScriptRoot -Parent) "requirements-memory.txt"
$out = if ($env:ARK_LIVE_DATA) { $env:ARK_LIVE_DATA } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
$offsets = Join-Path $out "config\memory_offsets.json"
$template = Join-Path (Split-Path $PSScriptRoot -Parent) "templates\memory_offsets.template.json"

pip install -r $req -q

Write-Host ""
Write-Host "=== ASA memory reader — community safety preflight ===" -ForegroundColor Cyan
python $preflight
if ($LASTEXITCODE -ne 0) {
    Write-Host "Preflight failed. Fix findings before attaching to the game." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "LIVE ATTACH RULES (read before continuing):" -ForegroundColor Yellow
Write-Host "  1. Singleplayer ONLY — not official, not player-hosted, not dedicated"
Write-Host "  2. Launch ASA with -NoBattlEye"
Write-Host "  3. Close other BattlEye-protected games (BEService.exe must not be running)"
Write-Host "  4. Tool is read-only — still risky on MP; gate blocks MP/BE signals"
Write-Host "  5. Run START_NETWORK_AUDIT.ps1 on first live session to verify no tool sockets"
Write-Host ""
$ack = Read-Host "Type SP-ONLY to continue (anything else aborts)"
if ($ack -ne "SP-ONLY") {
    Write-Host "Aborted." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $offsets)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $offsets) | Out-Null
    Copy-Item $template $offsets
    Write-Host "Created $offsets from template — fill offsets for your patch before expecting vitals."
}

Write-Host ""
Write-Host "SP-only memory reader (BattlEye must be OFF) -> $out\memory_digest.json"
Write-Host "Launch game: singleplayer with -NoBattlEye"
python $script --out-dir $out --interval 1
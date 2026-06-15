# Interactive SP offset mapper — read-only pymem scans.
# Maps health/stamina/etc. into local memory_offsets.json (gitignored).

$ErrorActionPreference = "Stop"
$preflight = Join-Path $PSScriptRoot "asa_safety_preflight.py"
$mapper = Join-Path $PSScriptRoot "asa_offset_mapper.py"
$req = Join-Path (Split-Path $PSScriptRoot -Parent) "requirements-memory.txt"
$out = if ($env:ARK_LIVE_DATA) { $env:ARK_LIVE_DATA } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }

pip install -r $req -q

Write-Host ""
Write-Host "=== ASA offset mapper — community safety preflight ===" -ForegroundColor Cyan
python $preflight
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "LIVE MAPPING RULES:" -ForegroundColor Yellow
Write-Host "  1. Singleplayer ONLY, launch with -NoBattlEye"
Write-Host "  2. Read-only scans — never freeze/write values in-game for mapping"
Write-Host "  3. Output stays local: $out\config\"
Write-Host ""
$ack = Read-Host "Type SP-ONLY to continue (anything else aborts)"
if ($ack -ne "SP-ONLY") {
    Write-Host "Aborted." -ForegroundColor Yellow
    exit 1
}

$env:ARK_LIVE_DATA = $out
if ($args.Count -eq 0) {
    python $mapper --out-dir $out guide
    Write-Host ""
    Write-Host "Example: python $mapper --out-dir $out scan health --value 100"
} else {
    python $mapper --out-dir $out @args
}
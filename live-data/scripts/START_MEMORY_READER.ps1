# ASA singleplayer memory reader (read-only).
# Requirements: SP session, BattlEye DISABLED (-NoBattlEye), offsets filled locally.
# Optional: $env:ARK_LIVE_DATA = "<local-data>\ARK_LiveData"
# Optional: $env:ARK_ASA_SAVED = "...\ShooterGame\Saved"

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "asa_memory_reader.py"
$req = Join-Path (Split-Path $PSScriptRoot -Parent) "requirements-memory.txt"
$out = if ($env:ARK_LIVE_DATA) { $env:ARK_LIVE_DATA } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
$offsets = Join-Path $out "config\memory_offsets.json"
$template = Join-Path (Split-Path $PSScriptRoot -Parent) "templates\memory_offsets.template.json"

pip install -r $req -q

if (-not (Test-Path $offsets)) {
    New-Item -ItemType Directory -Force -Path (Split-Path $offsets) | Out-Null
    Copy-Item $template $offsets
    Write-Host "Created $offsets from template — fill offsets for your patch before expecting vitals."
}

Write-Host "SP-only memory reader (BattlEye must be OFF) -> $out\memory_digest.json"
Write-Host "Launch game: singleplayer with -NoBattlEye"
python $script --out-dir $out --interval 1
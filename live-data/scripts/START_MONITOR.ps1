# Start ASA singleplayer game-state monitor (read-only).
# Launch the game AFTER this is running. Press Ctrl+C to stop.
# Optional: $env:ARK_LIVE_DATA = "D:\your\mirror\path"

$preflight = Join-Path $PSScriptRoot "asa_safety_preflight.py"
$script = Join-Path $PSScriptRoot "asa_game_state_monitor.py"
python $preflight
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$out = if ($env:ARK_LIVE_DATA) { $env:ARK_LIVE_DATA } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }

Write-Host "Starting monitor -> $out"
Write-Host "Live summary: $out\monitor_latest.json"
python $script --out-dir $out
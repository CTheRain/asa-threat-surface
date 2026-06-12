# Start ASA singleplayer game-state monitor (read-only).
# Launch the game AFTER this is running. Press Ctrl+C to stop.

$script = "C:\Users\SLAANESH\asa_game_state_monitor.py"
if (-not (Test-Path $script)) {
    $script = "S:\ARK_LiveData\scripts\asa_game_state_monitor.py"
}

Write-Host "Starting monitor -> S:\ARK_LiveData\"
Write-Host "Live summary: S:\ARK_LiveData\monitor_latest.json"
python $script
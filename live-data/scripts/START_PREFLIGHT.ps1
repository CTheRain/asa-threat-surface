# Offline safety checks before live memory attach. No game required.
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "asa_safety_preflight.py"
$req = Join-Path (Split-Path $PSScriptRoot -Parent) "requirements-memory.txt"

pip install -r $req -q
python $script
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
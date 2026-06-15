# Poll sockets for ArkAscended.exe + local Python research scripts.
# Run alongside SP session. Output: network_audit_latest.json (gitignored).

$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "asa_network_audit.py"
$out = if ($env:ARK_LIVE_DATA) { $env:ARK_LIVE_DATA } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }

Write-Host "Network audit -> $out\network_audit_latest.json"
Write-Host "Watching: ArkAscended.exe, python tooling. Ctrl+C to stop."
python $script --out-dir $out --interval 2
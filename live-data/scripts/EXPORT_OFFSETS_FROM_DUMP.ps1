# Convert latest Dumper-7 Dumpspace JSON -> live-data/config/memory_offsets.json
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "asa_dumper7_to_offsets.py"
$out = if ($env:ARK_LIVE_DATA) { $env:ARK_LIVE_DATA } else { (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
python $script --auto --out (Join-Path $out "config\memory_offsets.json")
# Rebuild Dumper-7.dll (x64 Release). Requires VS 2022 Build Tools + VCTools.
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent | Split-Path -Parent
$proj = Join-Path $root "tools\Dumper-7\Dumper\Dumper.vcxproj"
$msbuild = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe"
if (-not (Test-Path $msbuild)) {
    Write-Error "MSBuild not found. Install VS 2022 Build Tools with C++ workload."
}
& $msbuild $proj /p:Configuration=Release /p:Platform=x64 /m /v:minimal
$built = Join-Path $root "tools\Dumper-7\Dumper\x64\Release\Dumper-7.dll"
$dest = Join-Path $root "tools\Dumper-7\Dumper-7.dll"
Copy-Item $built $dest -Force
Write-Host "Built -> $dest"
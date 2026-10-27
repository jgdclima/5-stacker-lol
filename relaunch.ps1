<#
.SYNOPSIS
    Relaunches the League 5-Stack Coordinator Discord Bot and re-registers slash commands with Discord if any command definitions changed.
.EXAMPLE
    .\relaunch.ps1
    .\relaunch.ps1 --sync
    .\relaunch.ps1 --check-only
    .\relaunch.ps1 --foreground
#>
$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $ScriptDir ".venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    & $VenvPython (Join-Path $ScriptDir "relaunch.py") @args
} else {
    python (Join-Path $ScriptDir "relaunch.py") @args
}
exit $LASTEXITCODE

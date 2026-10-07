# Registers the studio to start with Windows and restart if it stops (a Scheduled Task; no extra software).
# Run from an elevated PowerShell in the repository root, after scripts\install.ps1 and after editing .env.
#   .\scripts\install-service.ps1            # install and start
#   .\scripts\install-service.ps1 -Remove    # stop and remove
param([switch]$Remove, [string]$TaskName = "ShunyaStudio")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if ($Remove) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "Removed scheduled task '$TaskName'."
    return
}

$exe = Join-Path $root ".venv\Scripts\shunya.exe"
if (-not (Test-Path $exe)) { throw "Run scripts\install.ps1 first ($exe not found)." }
if (-not (Test-Path (Join-Path $root ".env"))) { throw "Create .env first (copy .env.example) and set SHUNYA_API_TOKEN." }
if (-not (Select-String -Path (Join-Path $root ".env") -Pattern "^\s*SHUNYA_API_TOKEN\s*=\s*\S" -Quiet)) {
    throw "Set SHUNYA_API_TOKEN in .env before running the studio as a service."
}

# Unreal needs a logged-in desktop session for playtests and packaging smoke runs, so the task runs
# as the current user at logon rather than as SYSTEM at boot.
$action = New-ScheduledTaskAction -Execute $exe -Argument "serve" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Host "Scheduled task '$TaskName' installed and started. Logs: $root\data\logs\studio.log"
Write-Host "Check it with:  Invoke-RestMethod http://127.0.0.1:8400/health"

# Run the aolserver host at logon on Windows, via Task Scheduler.
#   powershell -ExecutionPolicy Bypass -File run\windows\install-task.ps1          install
#   powershell -ExecutionPolicy Bypass -File run\windows\install-task.ps1 -Remove  uninstall
param([switch]$Remove)
$repo = Resolve-Path "$PSScriptRoot\..\.."
$name = "aolserver"
if ($Remove) { Unregister-ScheduledTask -TaskName $name -Confirm:$false; "removed"; exit }
$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { $py = (Get-Command py -ErrorAction Stop).Source }
$action = New-ScheduledTaskAction -Execute $py -Argument "`"$repo\start.py`"" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit 0
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $name
"aolserver task installed and started (python $repo\start.py)"

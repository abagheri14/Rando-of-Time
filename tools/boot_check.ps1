# Starts Longshot and watches the log until it crashes or finishes loading resources, then closes the game.
param([int]$TimeoutSec = 150)
$ErrorActionPreference = 'Stop'
$root = 'E:\LongshotLauncher-data\builds\stable\v3.1.0'
$log = Join-Path $root 'logs\longshot_log.txt'
Get-Process longshot -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
$start = Get-Date
Start-Process -FilePath (Join-Path $root 'longshot.exe') -WorkingDirectory $root | Out-Null
$result = 'TIMEOUT'
while (((Get-Date) - $start).TotalSeconds -lt $TimeoutSec) {
    Start-Sleep -Seconds 1
    if ((Test-Path $log) -and ((Get-Item $log).LastWriteTime -gt $start)) {
        $text = Get-Content $log -Raw
        if ($text -match 'FATAL') {
            $result = 'CRASH'
            break
        }
        if ($text -match 'texts: mals/') {
            Start-Sleep -Seconds 5
            $text = Get-Content $log -Raw
            if ($text -match 'FATAL') {
                $result = 'CRASH (late)'
            } else {
                $result = 'BOOTED'
            }
            break
        }
    }
}
Get-Process longshot -ErrorAction SilentlyContinue | Stop-Process -Force
"$result after $([int]((Get-Date) - $start).TotalSeconds)s"
if (Test-Path $log) {
    Select-String -Path $log -Pattern 'FATAL|guest backtrace' |
        Select-Object -First 2 |
        ForEach-Object { $_.Line.Substring(0, [Math]::Min(160, $_.Line.Length)) }
}

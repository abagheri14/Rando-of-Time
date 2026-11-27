# Starts Longshot, watches its newest log and closes it again. Prints PASS, CRASH or TIMEOUT.
# The boot marker is the audio renderer opening, because that comes after the point where we've seen boots crash.
param([int]$Seconds = 40)
$rc = "E:\LongshotLauncher-data\builds\stable\v3.1.0"
$log = Join-Path $rc "logs\longshot_log.txt"
if (@(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like "$rc\*" }).Count) {
    "BUSY: a Longshot game is already running"
    exit
}
$before = if (Test-Path $log) { (Get-Item $log).LastWriteTime } else { Get-Date "2000-01-01" }
$p = Start-Process -FilePath (Join-Path $rc "longshot.exe") -WorkingDirectory $rc -PassThru
$result = "TIMEOUT"
for ($i = 0; $i -lt $Seconds * 2; $i++) {
    Start-Sleep -Milliseconds 500
    if (-not (Test-Path $log)) { continue }
    if ((Get-Item $log).LastWriteTime -le $before) { continue }
    $text = Get-Content $log -Raw -ErrorAction SilentlyContinue
    if ($text -match "CRASH: exception") {
        $result = "CRASH"
        break
    }
    if ($text -match "audio: renderer opened") {
        Start-Sleep -Seconds 3
        $text = Get-Content $log -Raw
        if ($text -match "CRASH: exception") {
            $result = "CRASH"
        } else {
            $result = "PASS"
        }
        break
    }
}
# The launcher starts a second exe in bin, so we close every process under the build folder.
Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like "$rc\*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2
$left = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -like "$rc\*" }).Count
"$result (processes left: $left)"

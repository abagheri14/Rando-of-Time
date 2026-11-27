# Builds tracker\dist\RandoOfTimeTracker.exe with the .NET Framework 4.8 compiler that comes with Windows 10/11,
# so the exe runs on those systems without an SDK or anything else to download.
# It compiles in the shared controls and embeds the per-monitor DPI manifest, the icon and the header logo.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$ui = Join-Path (Split-Path -Parent $here) "common\ui"
$csc = "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
$dist = Join-Path $here "dist"
New-Item -ItemType Directory -Force $dist | Out-Null
$src = @(Get-ChildItem (Join-Path $here "app") -Filter *.cs | ForEach-Object { $_.FullName }) + (Join-Path $ui "Ui.cs")
& $csc /nologo /target:winexe /optimize+ /out:"$dist\RandoOfTimeTracker.exe" `
    /win32manifest:"$ui\app.manifest" /win32icon:"$ui\tracker.ico" "/resource:$ui\tracker_256.png,RemakeUi.logo.png" `
    /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.Web.Extensions.dll /r:System.Core.dll $src
if ($LASTEXITCODE -ne 0) { throw "csc failed" }
"built $dist\RandoOfTimeTracker.exe"

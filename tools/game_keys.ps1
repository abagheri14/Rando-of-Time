# Brings Longshot to the front and sends it keys, using the mapping in user/longshot_options.ini.
# E is A, S/W move down/up and Return is +. Each step is key:wait, with the wait after the press in seconds.
# Example: powershell -File tools/game_keys.ps1 "e:1.5" "s:0.6" "e:2"
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Steps)
Add-Type @"
using System; using System.Runtime.InteropServices;
public class GameKeys {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);
  [DllImport("user32.dll")] public static extern uint MapVirtualKey(uint code, uint mapType);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern IntPtr FindWindow(string cls, string title);
}
"@
$h = [GameKeys]::FindWindow("Longshot", $null)  # the game window's class (the log names it)
if ($h -eq [IntPtr]::Zero) {
    $game = Get-Process longshot -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if (-not $game) {
        "no game window"
        exit 1
    }
    $h = $game.MainWindowHandle
}

# Tap Alt first, or Windows won't let a script bring the game to the front.
[GameKeys]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
[GameKeys]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
[GameKeys]::ShowWindow($h, 9) | Out-Null
[GameKeys]::SetForegroundWindow($h) | Out-Null
Start-Sleep -Milliseconds 400
$front = ([GameKeys]::GetForegroundWindow() -eq $h)
$vk = @{
    "e" = 0x45
    "s" = 0x53
    "w" = 0x57
    "a" = 0x41
    "d" = 0x44
    "return" = 0x0D
    "tab" = 0x09
    "m" = 0x4D
    "space" = 0x20
    "esc" = 0x1B
    "shift" = 0x10
}
foreach ($step in $Steps) {
    $k, $wait = $step.Split(":")
    $code = $vk[$k.ToLower()]
    if ($null -eq $code) {
        "unknown key $k"
        continue
    }
    $scan = [byte][GameKeys]::MapVirtualKey($code, 0)
    [GameKeys]::keybd_event([byte]$code, $scan, 0, [UIntPtr]::Zero)
    Start-Sleep -Milliseconds 120
    [GameKeys]::keybd_event([byte]$code, $scan, 2, [UIntPtr]::Zero)
    if ($wait) { Start-Sleep -Milliseconds ([int]([double]$wait * 1000)) }
}
"game window in front: $front; pressed: $($Steps -join ' ')"

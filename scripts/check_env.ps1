[CmdletBinding()]
param([switch]$JsonOut)
$rep = [ordered]@{}
$todo = [System.Collections.Generic.List[string]]::new()
function chk($k, [bool]$pass, $val, $msg, $td, [bool]$warn=$false) {
    $st = if ($pass) { 'PASS' } elseif ($warn) { 'WARN' } else { 'FAIL' }
    $rep[$k] = @{ status = $st; value = $val; note = $msg }
    if ($st -ne 'PASS' -and $td) { $todo.Add($td) }
}

$nv = try { (node -v 2>$null).Trim() } catch { $null }
chk 'node' ([bool]$nv) $nv $null "Node.js: Install Node.js LTS"

$gv = try { (git --version 2>$null).Trim() } catch { $null }
chk 'git' ([bool]$gv) $gv $null "Git: Install Git for Windows"

$ff = try { (ffmpeg -version 2>$null | Select-Object -First 1).Trim() } catch { $null }
$fp = try { (ffprobe -version 2>$null | Select-Object -First 1).Trim() } catch { $null }
chk 'ffmpeg' ([bool]$ff) $ff $null "ffmpeg: Download ffmpeg and add to PATH"
chk 'ffprobe' ([bool]$fp) $fp $null "ffprobe: Download ffprobe and add to PATH"

$py = try { (python --version 2>$null).Trim() } catch { $null }
$py0 = try { (py -0 2>$null | Out-String).Trim() } catch { $null }
chk 'python' ([bool]$py) $py $py0 "Python: Install Python 3.11+"

$pw = @("$env:LOCALAPPDATA\ms-playwright", "$env:USERPROFILE\AppData\Local\ms-playwright") | ForEach-Object { if (Test-Path $_) { Get-ChildItem $_ -Recurse -Filter "chrome-headless-shell.exe" -EA SilentlyContinue | Select-Object -First 1 } } | Select-Object -First 1
$pwPath = if ($pw) { $pw.FullName } else { $null }
chk 'playwright' ([bool]$pw) $pwPath $null "Playwright: playwright install chromium-headless-shell"

$w = (Get-Command "whisper-cli.exe" -EA SilentlyContinue).Source
$m = Get-ChildItem "C:\motion-agent\models" -Filter "*.bin" -EA SilentlyContinue | Select-Object -First 1
$mPath = if ($m) { $m.FullName } else { $null }
chk 'whisper' ([bool]($w -and $m)) $w $mPath "Whisper: Place whisper-cli.exe and ggml-*.bin model"

$sq = try { (python -c "import sqlite3; print(sqlite3.sqlite_version)" 2>$null).Trim() } catch { $null }
$sqOk = [bool]($sq -and [version]$sq -ge [version]'3.51.3')
chk 'sqlite' $sqOk $sq "required >= 3.51.3" "SQLite: Upgrade python sqlite3 >= 3.51.3 (found $sq)"

$ram = try { [math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB, 2) } catch { 0 }
chk 'ram' ($ram -ge 1.2) "$ram GB free" $null "RAM: Target >= 1.2 GB free (current $ram GB)" $true

$dsk = try { [math]::Round((Get-PSDrive C).Free / 1GB, 2) } catch { 0 }
chk 'disk' ($dsk -ge 10.0) "$dsk GB free" $null "Disk: Free at least 10 GB on C: (current $dsk GB)"

$pwr = try { (powercfg /getactivescheme 2>$null | Out-String).Trim() } catch { $null }
chk 'power_plan' ([bool]$pwr) $pwr $null "Power (Admin): powercfg /x standby-timeout-ac 0; hibernate-timeout-ac 0; disk-timeout-ac 0"

$pf = try { $s = 0; Get-CimInstance Win32_PageFileUsage -EA SilentlyContinue | ForEach-Object { $s += $_.AllocatedBaseSize }; $s } catch { 0 }
chk 'page_file' ($pf -ge 8192) "$pf MB" "target 8192-12288 MB" "Page file (Admin): Set fixed 8-12 GB pagefile" $true

$dex = try { (Get-MpPreference -EA Stop).ExclusionPath -contains "C:\motion-agent" } catch { $false }
chk 'defender_exclusion' $dex $dex $null "Defender (Admin): Add-MpPreference -ExclusionPath 'C:\motion-agent'"

if ($JsonOut) { $rep | ConvertTo-Json -Depth 4; exit 0 }
Write-Host "=== Environment Check (Phase P0a) ===" -ForegroundColor Cyan
foreach ($k in $rep.Keys) {
    $c = switch ($rep[$k].status) { 'PASS' {'Green'} 'WARN' {'Yellow'} default {'Red'} }
    Write-Host ("[{0,-4}] {1,-18} {2}" -f $rep[$k].status, $k, $rep[$k].value) -ForegroundColor $c
}
Write-Host "`n=== Actionable To-Do Items for User (Admin Steps) ===" -ForegroundColor Yellow
if ($todo.Count -eq 0) { Write-Host "All checks passed!" -ForegroundColor Green }
else { for ($i=0; $i -lt $todo.Count; $i++) { Write-Host ("{0}. {1}" -f ($i+1), $todo[$i]) } }

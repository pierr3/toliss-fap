# ToLiss FAP installer / uninstaller  (Windows PowerShell 5.1+, no other dependency)
#
# Installs the Flight Attendant Panel into a ToLiss A320 aircraft folder:
#   1. copies the plugin to   <aircraft>\plugins\ToLissFAP
#   2. copies the 3D panel to <aircraft>\objects\ToLissFAP
#   3. adds the clickable FAP screen to YOUR local cockpit OBJ (in X-Plane only the
#      cockpit object receives clicks). The untouched OBJ is kept as *.fap-original.
#   4. attaches the 3D panel in every .acf that uses that cockpit (backup written first).
# No ToLiss file is shipped: your own files are patched in place, always with backups.
#
# Usage: Install-FAP.ps1 [-Aircraft <folder>] [-Uninstall] [-PluginOnly] [-ExtraSounds <dir>] [-Force]
#
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 pierr3 and ToLiss FAP contributors
param(
    [string]$Aircraft,
    [switch]$Uninstall,
    [switch]$PluginOnly,       # only refresh the plugin folder (no OBJ / acf changes)
    [string]$ExtraSounds,      # optional folder merged into plugins\ToLissFAP\sounds
    [switch]$Force             # do not refuse while X-Plane is running
)
$ErrorActionPreference = "Stop"
$here = $PSScriptRoot
$L1 = [Text.Encoding]::GetEncoding(28591)   # .obj / .acf are 8-bit text
$inv = [Globalization.CultureInfo]::InvariantCulture

function Say([string]$s, [string]$c = "Gray") { Write-Host $s -ForegroundColor $c }
function Fail([string]$s) { Write-Host ""; Write-Host "ERROR: $s" -ForegroundColor Red; exit 1 }
function Read-L1([string]$p) { [IO.File]::ReadAllText($p, $L1) }
function Write-L1([string]$p, [string]$t) { [IO.File]::WriteAllText($p, $t, $L1) }
function Stamp { Get-Date -Format "yyyyMMdd-HHmmss" }
function Backup([string]$p) {
    $d = "$p.fapbak-$(Stamp)"
    Copy-Item -LiteralPath $p $d
    Say "  backup -> $d"
}

# ---------------------------------------------------------------- aircraft folder
function Test-Aircraft([string]$dir) {
    if (-not $dir -or -not (Test-Path -LiteralPath $dir)) { return $false }
    foreach ($a in Get-ChildItem -LiteralPath $dir -Filter *.acf -ErrorAction SilentlyContinue) {
        if ((Read-L1 $a.FullName) -match "(?m)^P _obja/\d+/_v10_att_file_stl kitchens\.obj\r?$") { return $true }
    }
    return $false
}

if (-not $Aircraft) {
    # try the usual Steam / default locations first
    $guess = @()
    foreach ($xp in "C:\Program Files (x86)\Steam\steamapps\common\X-Plane 12", "C:\X-Plane 12", "D:\X-Plane 12", "D:\SteamLibrary\steamapps\common\X-Plane 12", "E:\SteamLibrary\steamapps\common\X-Plane 12") {
        $acDir = Join-Path $xp "Aircraft"
        if (Test-Path -LiteralPath $acDir) {
            $guess += Get-ChildItem -LiteralPath $acDir -Directory -Recurse -Depth 1 -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -like "ToLissA320*" -and (Test-Aircraft $_.FullName) }
        }
    }
    if (@($guess).Count -eq 1) {
        $Aircraft = $guess[0].FullName
        Say "Found ToLiss A320: $Aircraft" "Cyan"
    } else {
        Add-Type -AssemblyName System.Windows.Forms
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        $dlg.Description = "Select your ToLiss A320 folder (the one that contains a320.acf)"
        $dlg.ShowNewFolderButton = $false
        if ($dlg.ShowDialog() -ne "OK") { Fail "No folder selected." }
        $Aircraft = $dlg.SelectedPath
    }
}
$Aircraft = $Aircraft.TrimEnd('\')
if (-not (Test-Aircraft $Aircraft)) {
    Fail "'$Aircraft' does not look like a ToLiss A320 folder (no .acf with kitchens.obj found)."
}
if (-not $Force -and (Get-Process -Name "X-Plane*" -ErrorAction SilentlyContinue)) {
    Fail "X-Plane is running. Please close X-Plane first, then run this again."
}

# the .acf used to read attachment positions: prefer the standard-definition one
$acfs = @(Get-ChildItem -LiteralPath $Aircraft -Filter *.acf)
$refAcf = $acfs | Where-Object { $_.Name -eq "a320_StdDef.acf" } | Select-Object -First 1
if (-not $refAcf) { $refAcf = $acfs | Where-Object { (Read-L1 $_.FullName) -match "kitchens\.obj" } | Select-Object -First 1 }
$refText = Read-L1 $refAcf.FullName

function Get-Attach([string]$text, [string]$file) {
    $m = [regex]::Match($text, "(?m)^P _obja/(\d+)/_v10_att_file_stl " + [regex]::Escape($file) + "\r?$")
    if (-not $m.Success) { Fail "$file attachment not found in $($refAcf.Name)" }
    $i = $m.Groups[1].Value
    $v = @{}
    foreach ($k in "x", "y", "z") {
        $v[$k] = [double]::Parse([regex]::Match($text, "(?m)^P _obja/$i/_v10_att_${k}_acf_prt_ref (\S+)").Groups[1].Value, $inv)
    }
    return $v
}
$ckRel = [regex]::Match($refText, "(?m)^P _obja/0/_v10_att_file_stl (.+?)\r?$").Groups[1].Value.Trim()
$ckObj = [IO.Path]::GetFullPath((Join-Path (Join-Path $Aircraft "objects") $ckRel))
if (-not (Test-Path -LiteralPath $ckObj)) { Fail "cockpit object not found: $ckObj" }

# ---------------------------------------------------------------- cockpit OBJ patch
function Get-Pristine([string]$obj) {
    # The untouched original; created on first use. If the live OBJ has no FAP block
    # (fresh install or ToLiss update) it becomes the new original.
    $ip = "$obj.fapinfo"
    if ((Test-Path -LiteralPath $ip) -and (Read-L1 $obj).Contains("ToLissFAP")) {
        $orig = (Get-Content -LiteralPath $ip -Raw | ConvertFrom-Json).original
        if ($orig -and (Test-Path -LiteralPath $orig)) { return $orig }
    }
    $orig = "$obj.fap-original"
    Copy-Item -LiteralPath $obj $orig -Force
    (@{ original = $orig } | ConvertTo-Json) | Set-Content -LiteralPath $ip -Encoding ASCII
    Say "  original saved -> $orig"
    return $orig
}

function Add-FapScreen([string]$obj, [string]$fap, [double]$dx, [double]$dy, [double]$dz) {
    $base = Read-L1 (Get-Pristine $obj)
    if ($base.Contains("ToLissFAP")) { Fail "the recorded original of $obj already contains ToLissFAP" }
    # parse our screen OBJ
    $vts = New-Object System.Collections.Generic.List[string]
    $idx = New-Object System.Collections.Generic.List[int]
    $cmds = New-Object System.Collections.Generic.List[string]
    $afterIdx = $false
    foreach ($line in ((Read-L1 $fap) -split "`r?`n")) {
        $t = $line.Trim()
        if ($t -eq "" -or $t.StartsWith("#")) { continue }
        $p = $t -split "\s+"
        if ($p[0] -eq "VT") {
            $xyz = @(
                ([double]::Parse($p[1], $inv) + $dx).ToString("F6", $inv),
                ([double]::Parse($p[2], $inv) + $dy).ToString("F6", $inv),
                ([double]::Parse($p[3], $inv) + $dz).ToString("F6", $inv))
            $vts.Add("VT`t" + (($xyz + $p[4..($p.Count - 1)]) -join "`t"))
        } elseif ($p[0] -eq "IDX" -or $p[0] -eq "IDX10") {
            foreach ($v in $p[1..($p.Count - 1)]) { $idx.Add([int]$v) }
            $afterIdx = $true
        } elseif ($afterIdx) {
            $cmds.Add($t)
        }
    }
    $text = $base
    $nl = "`n"; if ($text.Contains("`r`n")) { $nl = "`r`n" }
    $ml = [Text.RegularExpressions.RegexOptions]::Multiline
    $rl = [Text.RegularExpressions.RegexOptions]"Multiline, RightToLeft"
    $m = [regex]::Match($text, "^POINT_COUNTS[ \t]+(\d+)[ \t]+(\d+)[ \t]+(\d+)[ \t]+(\d+)", $ml)
    if (-not $m.Success) { Fail "POINT_COUNTS not found in $obj" }
    $nvt = [int]$m.Groups[1].Value; $nidx = [int]$m.Groups[4].Value
    # vertices after the last VT line
    $lv = [regex]::Match($text, "^VT[ \t][^\r\n]*\r?\n", $rl)
    $e = $lv.Index + $lv.Length
    $text = $text.Substring(0, $e) + ($vts -join $nl) + $nl + $text.Substring($e)
    # indices after the last IDX / IDX10 line
    $li = [regex]::Match($text, "^IDX(?:10)?[ \t][^\r\n]*\r?\n", $rl)
    $e = $li.Index + $li.Length
    $lines = New-Object System.Collections.Generic.List[string]
    for ($k = 0; $k -lt $idx.Count; $k += 10) {
        $n = [Math]::Min(10, $idx.Count - $k)
        $chunk = @(); for ($j = 0; $j -lt $n; $j++) { $chunk += ($idx[$k + $j] + $nvt) }
        if ($n -eq 10) { $lines.Add("IDX10`t" + ($chunk -join "`t")) } else { foreach ($c in $chunk) { $lines.Add("IDX`t$c") } }
    }
    $text = $text.Substring(0, $e) + ($lines -join $nl) + $nl + $text.Substring($e)
    # commands appended at the very end, TRIS offsets shifted
    $out = foreach ($c in $cmds) {
        $p = $c -split "\s+"
        if ($p[0] -eq "TRIS") { "TRIS`t$([int]$p[1] + $nidx)`t$($p[2])" } else { $c }
    }
    if (-not $text.EndsWith($nl)) { $text += $nl }
    $text += "# ToLissFAP-begin (flight attendant panel screen)" + $nl + "ATTR_draw_enable" + $nl + ($out -join $nl) + $nl + "# ToLissFAP-end" + $nl
    $re = New-Object System.Text.RegularExpressions.Regex("^(POINT_COUNTS[ \t]+)\d+([ \t]+\d+[ \t]+\d+[ \t]+)\d+", $ml)
    $newVt = $nvt + $vts.Count; $newIdx = $nidx + $idx.Count
    $text = $re.Replace($text, { param($g) $g.Groups[1].Value + $newVt + $g.Groups[2].Value + $newIdx }, 1)

    if ($text -eq (Read-L1 $obj)) { Say "  cockpit OBJ already up to date"; return }
    Backup $obj
    Write-L1 $obj $text
    Say "  cockpit OBJ patched: +$($vts.Count) vertices, +$($idx.Count) indices" "Green"
}

function Remove-FapScreen([string]$obj) {
    $ip = "$obj.fapinfo"
    if (-not (Test-Path -LiteralPath $ip)) { Say "  cockpit OBJ not patched, nothing to restore"; return }
    $orig = (Get-Content -LiteralPath $ip -Raw | ConvertFrom-Json).original
    if (-not (Test-Path -LiteralPath $orig)) { Fail "original cockpit OBJ missing: $orig" }
    if ((Read-L1 $obj).Contains("ToLissFAP")) {
        Backup $obj
        Copy-Item -LiteralPath $orig $obj -Force
        Say "  cockpit OBJ restored from $orig" "Green"
    } else {
        Say "  cockpit OBJ has no FAP block (already restored or updated by ToLiss)"
    }
    Remove-Item -LiteralPath $ip
}

# ---------------------------------------------------------------- .acf attachment
function Remove-FapAttachment([string]$t) {
    $m = [regex]::Match($t, "(?m)^P _obja/(\d+)/_v10_att_file_stl ToLissFAP/fap_hw\.obj\r?$")
    if (-not $m.Success) { return $t }
    $n = [int]$m.Groups[1].Value
    $cm = [regex]::Match($t, "(?m)^P _obja/count (\d+)")
    $cnt = [int]$cm.Groups[1].Value
    $t = [regex]::Replace($t, "(?m)^P _obja/$n/[^\n]*\n", "")
    $t = [regex]::Replace($t, "(?m)^P _obja/(\d+)/", {
        param($g) $k = [int]$g.Groups[1].Value
        if ($k -gt $n) { "P _obja/$($k - 1)/" } else { $g.Value } })
    return [regex]::Replace($t, "(?m)^P _obja/count \d+", "P _obja/count $($cnt - 1)")
}

function Add-FapAttachment([string]$t) {
    if ($t.Contains("ToLissFAP/fap_hw.obj")) { return $t }
    $km = [regex]::Match($t, "(?m)^P _obja/(\d+)/_v10_att_file_stl kitchens\.obj\r?$")
    if (-not $km.Success) { return $t }
    $k = $km.Groups[1].Value
    $cm = [regex]::Match($t, "(?m)^P _obja/count (\d+)")
    $n = [int]$cm.Groups[1].Value
    $lines = foreach ($x in [regex]::Matches($t, "(?m)^P _obja/$k/([^\r\n]+)")) {
        $prop = $x.Groups[1].Value
        if ($prop -like "_v10_att_file_stl *") { $prop = "_v10_att_file_stl ToLissFAP/fap_hw.obj" }
        "P _obja/$n/$prop"
    }
    return $t.Remove($cm.Index, $cm.Length).Insert($cm.Index, (($lines -join "`n") + "`n") + "P _obja/count $($n + 1)")
}

function Update-Acfs([bool]$add) {
    foreach ($a in $acfs) {
        $t = Read-L1 $a.FullName
        $ck0 = [regex]::Match($t, "(?m)^P _obja/0/_v10_att_file_stl (.+?)\r?$").Groups[1].Value.Trim()
        if ($ck0 -ne $ckRel) { continue }          # other cockpit (e.g. XP11 variants)
        $new = Remove-FapAttachment $t
        if ($add) { $new = Add-FapAttachment $new }
        if ($new -ne $t) {
            Backup $a.FullName
            Write-L1 $a.FullName $new
            if ($add) { Say "  $($a.Name): 3D panel attached" "Green" } else { Say "  $($a.Name): 3D panel removed" "Green" }
        }
    }
}

$plug = Join-Path $Aircraft "plugins\ToLissFAP"
$objDir = Join-Path $Aircraft "objects\ToLissFAP"

# ---------------------------------------------------------------- uninstall
if ($Uninstall) {
    Say "Removing ToLiss FAP from $Aircraft" "Cyan"
    Remove-FapScreen $ckObj
    Update-Acfs $false
    foreach ($d in $plug, $objDir) {
        if (Test-Path -LiteralPath $d) {
            try { Remove-Item -LiteralPath $d -Recurse -Force; Say "  deleted $d" }
            catch { Say "  could not delete $d (close X-Plane and delete it by hand)" "Yellow" }
        }
    }
    Say ""; Say "ToLiss FAP removed." "Green"
    exit 0
}

# ---------------------------------------------------------------- install
Say "Installing ToLiss FAP into $Aircraft" "Cyan"
Get-ChildItem -LiteralPath $here -Recurse -File | Unblock-File -ErrorAction SilentlyContinue

Say "Plugin"
$srcPlug = Join-Path $here "plugin\ToLissFAP"
$xpl = Join-Path $plug "win_x64\ToLissFAP.xpl"
if (Test-Path -LiteralPath $xpl) {
    try { Remove-Item -LiteralPath $xpl -Force }
    catch { Rename-Item -LiteralPath $xpl ("ToLissFAP.xpl.old-" + (Stamp)); Say "  (plugin was in use; reload the aircraft)" "Yellow" }
}
Get-ChildItem -LiteralPath (Join-Path $plug "win_x64") -Filter "*.old-*" -ErrorAction SilentlyContinue | Remove-Item -ErrorAction SilentlyContinue
robocopy $srcPlug $plug /E /XD (Join-Path $srcPlug "sounds") /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "copying the plugin failed (robocopy $LASTEXITCODE)" }
# sounds: only add files that are not there yet, so sounds the user replaced or added survive updates
robocopy (Join-Path $srcPlug "sounds") (Join-Path $plug "sounds") /E /XC /XN /XO /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { Fail "copying the sounds failed (robocopy $LASTEXITCODE)" }
if ($ExtraSounds) {
    robocopy $ExtraSounds (Join-Path $plug "sounds") /E /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Fail "copying extra sounds failed (robocopy $LASTEXITCODE)" }
}
$global:LASTEXITCODE = 0
Say "  -> $plug" "Green"
if ($PluginOnly) { exit 0 }

Say "Cockpit screen"
# the FAP geometry is expressed in the kitchens.obj frame; shift it into the cockpit frame
$kit = Get-Attach $refText "kitchens.obj"
$ck = Get-Attach $refText $ckRel
$ft = 0.3048
Add-FapScreen $ckObj (Join-Path $here "fap_screen.obj") (($kit.x - $ck.x) * $ft) (($kit.y - $ck.y) * $ft) (($kit.z - $ck.z) * $ft)

Say "3D panel"
New-Item -ItemType Directory -Force $objDir | Out-Null
Copy-Item (Join-Path $here "objects\ToLissFAP\*") $objDir -Force
Say "  -> $objDir" "Green"
Update-Acfs $true

Say ""
Say "Done! Start X-Plane and load the ToLiss A320." "Green"
Say "Run this again after every ToLiss update (updates replace the patched files)."

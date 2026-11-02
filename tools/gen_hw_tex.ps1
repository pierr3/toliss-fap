# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 pierr3 and ToLiss FAP contributors
# Draws the FAP hardware texture atlas (fap_hw.png, with alpha) and its lighting layer
# (fap_hw_LIT.png). Body blocks get a lit copy (driven by the ToLiss cabin lighting,
# like kitchens_LIT); legend / EMER overlays are transparent decals whose LIT is the
# backlit glow (driven per key). Block layout must match ATLAS in tools/build_fap_hw.py.
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $PSScriptRoot
$S = 1024
$fmt = [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
$day = New-Object System.Drawing.Bitmap $S, $S, $fmt
$lit = New-Object System.Drawing.Bitmap $S, $S, $fmt
$g = [System.Drawing.Graphics]::FromImage($day)
$l = [System.Drawing.Graphics]::FromImage($lit)
foreach ($gr in $g, $l) { $gr.SmoothingMode = "AntiAlias"; $gr.TextRenderingHint = "AntiAliasGridFit" }
$g.Clear([System.Drawing.Color]::FromArgb(0, 0, 0, 0))
$l.Clear([System.Drawing.Color]::Black)

function C($hex, $a = 255) { $c = [System.Drawing.ColorTranslator]::FromHtml($hex); [System.Drawing.Color]::FromArgb($a, $c.R, $c.G, $c.B) }
function Fill($gr, $col, $x, $y, $w, $h) { $b = New-Object System.Drawing.SolidBrush $col; $gr.FillRectangle($b, $x, $y, $w, $h); $b.Dispose() }
function Grad($gr, $top, $bot, $x, $y, $w, $h, $angle = 90) {
    $r = New-Object System.Drawing.Rectangle $x, $y, $w, $h
    $b = New-Object System.Drawing.Drawing2D.LinearGradientBrush $r, $top, $bot, $angle
    $gr.FillRectangle($b, $r); $b.Dispose()
}
function Noise($x, $y, $w, $h, $amp, $seed) {
    $rnd = New-Object System.Random $seed
    for ($i = 0; $i -lt ($w * $h / 5); $i++) {
        $px = $x + $rnd.Next($w); $py = $y + $rnd.Next($h); $c = $day.GetPixel($px, $py); $d = $rnd.Next(-$amp, $amp + 1)
        $day.SetPixel($px, $py, [System.Drawing.Color]::FromArgb($c.A, [Math]::Max(0, [Math]::Min(255, $c.R + $d)), [Math]::Max(0, [Math]::Min(255, $c.G + $d)), [Math]::Max(0, [Math]::Min(255, $c.B + $d))))
    }
}
function Edge($x, $y, $w, $h, $light, $dark, $px) {   # bevel shading: light top/left, dark bottom/right
    Fill $g (C $light 110) $x $y $w $px; Fill $g (C $light 80) $x $y $px $h
    Fill $g (C $dark 120) $x ($y + $h - $px) $w $px; Fill $g (C $dark 90) ($x + $w - $px) $y $px $h
}
function Text($gr, $txt, $col, $x, $y, $w, $h, $size) {
    $f = New-Object System.Drawing.Font "Arial Narrow", $size, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
    $b = New-Object System.Drawing.SolidBrush $col
    $sf = New-Object System.Drawing.StringFormat; $sf.Alignment = "Center"; $sf.LineAlignment = "Center"
    $gr.DrawString($txt, $f, $b, (New-Object System.Drawing.RectangleF $x, $y, $w, $h), $sf); $f.Dispose(); $b.Dispose()
}
function Glow($txt, $hex, $x, $y, $w, $h, $size) {      # soft halo + bright core on the LIT layer
    foreach ($o in @(@(-2, 0), @(2, 0), @(0, -2), @(0, 2), @(-1, -1), @(1, 1))) { Text $l $txt (C $hex 70) ($x + $o[0]) ($y + $o[1]) $w $h $size }
    Text $l $txt (C $hex) $x $y $w $h $size
}

# ---------------- row 0: large body blocks (256 x 256) ----------------
Fill $g (C "#a8a8a5") 0 0 256 256;                    Noise 0 0 256 256 2 1   # module: neutral light grey (grain from the normal map)
Fill $g (C "#9c9fa2") 256 0 256 256;                  Noise 256 0 256 256 3 2      # bezel (metal grey, flat)

Fill $g (C "#26282b") 512 0 256 256                                                  # dark
Fill $g (C "#66696d") 768 0 256 256;                  Noise 768 0 256 256 3 3   # key strip (uniform mid-dark plastic)
# ---------------- row 1: small body blocks (y 256..384) ----------------
Fill $g (C "#a4a7aa") 0 256 256 128                                                 # lip (shading comes from its rounded normals)
Grad $g (C "#c9ccce") (C "#a7aaad") 256 256 128 128; Edge 256 256 128 128 "#ffffff" "#4a4c4f" 6   # key frame
Grad $g (C "#6e7175") (C "#484b4f") 384 256 128 128; Edge 384 256 128 128 "#9a9da1" "#1d1e20" 7   # key cap
Grad $g (C "#de3127") (C "#9e140e") 512 256 128 128; Edge 512 256 128 128 "#ff9a90" "#4a0805" 7   # EMER cap
Fill $g (C "#0c0d0e") 640 256 128 128; Fill $g (C "#2e3135") 652 300 104 40; Fill $g (C "#c9ccce") 660 314 88 12   # USB
Fill $g (C "#1d1f21") 768 256 64 64                                                  # hole
Grad $g (C "#5d4a1e") (C "#2a2008") 832 256 64 64                                    # LED lens (unlit amber)
# lit body copy (cabin lighting): rows 0-1, full width, at ~40 % of the day colour
# (matches the absolute level of ToLiss kitchens_LIT on the same panel: ~85/255)
$LITK = 0.40
for ($y = 0; $y -lt 384; $y++) { for ($x = 0; $x -lt 1024; $x++) {
    $c = $day.GetPixel($x, $y); if ($c.A -eq 0) { continue }
    $lum = ($c.R + $c.G + $c.B) / 765.0
    $k = $LITK + 0.35 * (1 - $lum)          # dark parts (caps, strip) keep more of their colour
    $lit.SetPixel($x, $y, [System.Drawing.Color]::FromArgb(255, [int][Math]::Min(255, $c.R * $k), [int][Math]::Min(255, $c.G * $k), [int][Math]::Min(255, $c.B * $k * 0.97)))
} }
# ---------------- row 2: EMER legend decal (y 384..512, 256 x 128) ----------------
Text $g "EMER" (C "#f6f6f6" 235) 0 384 256 128 64
Fill $l (C "#ff2a14" 255) 24 400 208 96; Glow "EMER" "#ffffff" 0 384 256 128 64     # backlit red when active (kept off the block edges)
# ---------------- row 3: 8 key legend decals (y 512..640, 128 x 128) ----------------
$keys = @("", "LIGHTS`nMAIN`nON/OFF", "LAV`nMAINT", "SCREEN`n30 sec`nLOCK", "EVAC`nCMD", "EVAC`nRESET", "SMOKE`nRESET", "")
$cols = @("#000000", "#3dff4a", "#ff6a1e", "#ff6a1e", "#ff3a24", "#ff6a1e", "#ff6a1e", "#000000")
for ($k = 0; $k -lt 8; $k++) {
    if (-not $keys[$k]) { continue }
    $x = $k * 128; $c = C $cols[$k]
    $dim = [System.Drawing.Color]::FromArgb(245, [int]($c.R * 0.80 + 35), [int]($c.G * 0.80 + 35), [int]($c.B * 0.80 + 35))
    Text $g $keys[$k] $dim $x 512 128 128 27
    Glow $keys[$k] $cols[$k] $x 512 128 128 27
}
$day.Save((Join-Path $root "obj\fap_hw.png"), [System.Drawing.Imaging.ImageFormat]::Png)
$lit.Save((Join-Path $root "obj\fap_hw_LIT.png"), [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $l.Dispose(); $day.Dispose(); $lit.Dispose()
"wrote obj\fap_hw.png and obj\fap_hw_LIT.png"

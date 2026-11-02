# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 pierr3 and ToLiss FAP contributors
# Default "screen off" image for the FAP (html/img/screen_off_default.png, 1100 x 840):
# deep blue background with a simple AIRBUS wordmark. Liveries can override it with
# <livery>/FAP/screen_off.png (or .jpg).
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $PSScriptRoot
$W, $H = 1100, 840
$bmp = New-Object System.Drawing.Bitmap $W, $H
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = "AntiAlias"; $g.TextRenderingHint = "AntiAliasGridFit"

# background: deep navy, slightly lighter in the centre
$rect = New-Object System.Drawing.Rectangle 0, 0, $W, $H
$bg = New-Object System.Drawing.Drawing2D.LinearGradientBrush $rect, ([System.Drawing.ColorTranslator]::FromHtml("#0a1f44")), ([System.Drawing.ColorTranslator]::FromHtml("#020a1a")), 90
$g.FillRectangle($bg, $rect)
$path = New-Object System.Drawing.Drawing2D.GraphicsPath
$path.AddEllipse(-200, -150, $W + 400, $H + 300)
$glow = New-Object System.Drawing.Drawing2D.PathGradientBrush $path
$glow.CenterColor = [System.Drawing.Color]::FromArgb(90, 40, 80, 150)
$glow.SurroundColors = @([System.Drawing.Color]::FromArgb(0, 0, 0, 0))
$g.FillRectangle($glow, $rect)

# wordmark: wide-tracked bold capitals
$font = New-Object System.Drawing.Font "Arial", 120, ([System.Drawing.FontStyle]::Bold), ([System.Drawing.GraphicsUnit]::Pixel)
$white = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(240, 255, 255, 255))
$letters = "AIRBUS".ToCharArray()
$track = 26
$widths = $letters | ForEach-Object { $g.MeasureString([string]$_, $font, 1000, [System.Drawing.StringFormat]::GenericTypographic).Width }
$total = ($widths | Measure-Object -Sum).Sum + $track * ($letters.Count - 1)
$x = ($W - $total) / 2; $y = $H / 2 - 80
for ($i = 0; $i -lt $letters.Count; $i++) {
    $g.DrawString([string]$letters[$i], $font, $white, $x, $y, [System.Drawing.StringFormat]::GenericTypographic)
    $x += $widths[$i] + $track
}
# thin rule under the wordmark
$pen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(120, 255, 255, 255)), 2
$g.DrawLine($pen, ($W - $total) / 2, $y + 150, ($W + $total) / 2, $y + 150)

New-Item -ItemType Directory -Force (Join-Path $root "html\img") | Out-Null
$out = Join-Path $root "html\img\screen_off_default.png"
$bmp.Save($out, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
"wrote $out"

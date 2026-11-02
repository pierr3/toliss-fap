# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 pierr3 and ToLiss FAP contributors
# Builds the release folder + zip:  dist\ToLissFAP-<version>\  and  dist\ToLissFAP-<version>.zip
# Run build.bat first.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$ver = [regex]::Match((Get-Content -Raw "$root\src\fap.cpp"), '#define FAP_VERSION "([^"]+)"').Groups[1].Value
$xpl = "$root\build\ToLissFAP.xpl"
if (-not (Test-Path $xpl)) { throw "build\ToLissFAP.xpl missing - run build.bat first" }

$name = "ToLissFAP-$ver"
$out = "$root\dist\$name"
if (Test-Path $out) { Remove-Item $out -Recurse -Force }
$files = "$out\files"
$plug = "$files\plugin\ToLissFAP"
New-Item -ItemType Directory -Force "$plug\win_x64", "$files\objects\ToLissFAP" | Out-Null

Copy-Item $xpl "$plug\win_x64\"
Copy-Item "$root\html" "$plug\html" -Recurse
Copy-Item "$root\sounds" "$plug\sounds" -Recurse
Copy-Item "$root\LIVERY_FAP.txt", "$root\LICENSE" "$plug\"
Copy-Item "$root\obj\fap_hw.obj", "$root\obj\fap_hw.png", "$root\obj\fap_hw_LIT.png", "$root\obj\fap_hw_NML.png" "$files\objects\ToLissFAP\"
Copy-Item "$root\obj\fap_screen.obj", "$root\installer\Install-FAP.ps1" "$files\"
Copy-Item "$root\installer\Install FAP.bat", "$root\installer\Uninstall FAP.bat" "$out\"
Copy-Item "$root\docs\USER_GUIDE.md" "$out\USER GUIDE.txt"
Copy-Item "$root\LICENSE" "$out\LICENSE.txt"

$zip = "$root\dist\$name.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $out -DestinationPath $zip
"packaged $zip"

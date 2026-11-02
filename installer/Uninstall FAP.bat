@echo off
title ToLiss FAP - Uninstall
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0files\Install-FAP.ps1" -Uninstall %*
echo.
pause

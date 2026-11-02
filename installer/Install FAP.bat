@echo off
title ToLiss FAP - Install
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0files\Install-FAP.ps1" %*
echo.
pause

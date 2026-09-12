@echo off
title WiZ-Rescue: 1-Click Philips WiZ Auto-Fix
echo ================================================================
echo   Launching WiZ-Rescue Auto-Fix Engine...
echo ================================================================
powershell -ExecutionPolicy Bypass -File "%~dp0wiz_rescue.ps1"
echo.
pause

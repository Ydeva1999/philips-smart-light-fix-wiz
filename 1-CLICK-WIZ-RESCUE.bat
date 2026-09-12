@echo off
title Philips Smart Light (WiZ): 1-Click Auto-Fix
echo ================================================================
echo   Launching Philips Smart Light (WiZ) Auto-Fix Engine...
echo ================================================================
powershell -ExecutionPolicy Bypass -File "%~dp0wiz_rescue.ps1"
echo.
pause

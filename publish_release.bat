@echo off
chcp 65001 >NUL
title "HMS Release Publisher & GitHub Builder"
powershell -ExecutionPolicy Bypass -File "%~dp0publish_release.ps1"
pause

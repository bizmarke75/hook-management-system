@echo off
setlocal
echo Building HMS v3.14...
python build_exe.py
if errorlevel 1 (
    echo [ERROR] Build failed.
    exit /b %ERRORLEVEL%
)
echo [SUCCESS] Build completed.

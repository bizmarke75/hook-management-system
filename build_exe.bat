@echo off
echo ============================================================
echo   HMS Master GUI v2.6.0 - PyInstaller Executable Builder
echo ============================================================
echo.

:: Check PyInstaller
python -c "import PyInstaller" 2>NUL
if %ERRORLEVEL% NEQ 0 (
    echo [!] PyInstaller not found. Installing pyinstaller...
    pip install pyinstaller
)

echo [*] Building hms_master_gui.exe ...
pyinstaller --noconsole --onefile --name="hms_master_gui" hms_master_gui.py

echo.
if exist "dist\hms_master_gui.exe" (
    echo ============================================================
    echo [SUCCESS] Executable generated at: dist\hms_master_gui.exe
    echo ============================================================
) else (
    echo [ERROR] Build failed. Please check log messages above.
)
pause

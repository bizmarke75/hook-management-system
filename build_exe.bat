@echo off
echo ============================================================
echo   HMS Master GUI v2.8.0 - PyInstaller Executable Builder
echo ============================================================
echo.

:: Check PyInstaller
python -c "import PyInstaller" 2>NUL
if %ERRORLEVEL% NEQ 0 (
    echo [!] PyInstaller not found. Installing pyinstaller...
    pip install pyinstaller
)

echo [*] Building hms_master_gui.exe ...
if exist "337west_icon.ico" (
    pyinstaller --noconsole --onefile --name="hms_master_gui" --icon="337west_icon.ico" --add-data="337west_icon.ico;." hms_master_gui.py
) else (
    pyinstaller --noconsole --onefile --name="hms_master_gui" hms_master_gui.py
)

echo.
if exist "dist\hms_master_gui.exe" (
    echo ============================================================
    echo [SUCCESS] Executable generated at: dist\hms_master_gui.exe
    echo ============================================================
) else (
    echo [ERROR] Build failed. Please check log messages above.
)
pause

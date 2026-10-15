@echo off
echo ============================================================
echo HMS Master GUI Executable Builder (PyInstaller v2.6.0)
echo ============================================================
echo.

:: Install PyInstaller if missing
pip install pyinstaller

echo.
echo Building standalone hms_master_gui.exe with 337West icon...
pyinstaller --noconsole --onefile --icon="337west_icon.ico" --name="hms_master_gui" hms_master_gui.py

echo.
echo ============================================================
if exist "dist\hms_master_gui.exe" (
    echo SUCCESS! Executable built at: dist\hms_master_gui.exe
) else (
    echo BUILD FAILED. Check PyInstaller error logs above.
)
echo ============================================================
pause

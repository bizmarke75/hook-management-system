# ==============================================================================
# HMS v2.8.0 Auto-Fixer & ZIP Packager
# Run from your hook-management-system repository root:
#   powershell -ExecutionPolicy Bypass -File .\update_and_zip_hms.ps1
# ==============================================================================

$ErrorActionPreference = "Stop"
$RepoRoot = Get-Location
Write-Host "Applying HMS v2.8.0 fixes in: $RepoRoot" -ForegroundColor Cyan

# Ensure subdirectories exist
New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot ".github\workflows") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RepoRoot "docs") | Out-Null

# 1. build_exe.py
$buildExePy = @'
import os
import subprocess
import sys

def build():
    print("=" * 60)
    print("  HMS Master GUI v2.8.0 - Standalone Executable Builder")
    print("=" * 60)

    try:
        import PyInstaller
    except ImportError:
        print("[*] Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--name=hms_master_gui",
    ]

    if os.path.exists("337west_icon.ico"):
        cmd.extend([
            "--icon=337west_icon.ico",
            "--add-data=337west_icon.ico;."
        ])

    cmd.append("hms_master_gui.py")

    print("[*] Running command:", " ".join(cmd))
    res = subprocess.call(cmd)

    if res == 0:
        exe_path = os.path.abspath(os.path.join("dist", "hms_master_gui.exe"))
        print("\n" + "=" * 60)
        print(f" SUCCESS! Compiled executable ready at:\n {exe_path}")
        print("=" * 60)
    else:
        print("\n [ERROR] Build failed.")
        sys.exit(res)

if __name__ == "__main__":
    build()
'@
Set-Content -Path "build_exe.py" -Value $buildExePy -Encoding UTF8

# 2. build_exe.bat
$buildExeBat = @'
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
'@
Set-Content -Path "build_exe.bat" -Value $buildExeBat -Encoding UTF8

# 3. build_release.yml (placed in both root and .github/workflows/)
$buildReleaseYml = @'
name: Build and Package Release EXE

on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest
    permissions:
      contents: write

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Build Executable with PyInstaller
        run: |
          python build_exe.py

      - name: Create GitHub Release and Upload EXE
        uses: softprops/action-gh-release@v2
        if: startsWith(github.ref, 'refs/tags/')
        with:
          files: dist/hms_master_gui.exe
          name: HMS Release ${{ github.ref_name }}
          body_path: CHANGELOG.md
          draft: false
          prerelease: false
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
'@
Set-Content -Path "build_release.yml" -Value $buildReleaseYml -Encoding UTF8
Set-Content -Path ".github\workflows\build_release.yml" -Value $buildReleaseYml -Encoding UTF8

# 4. publish_release.ps1
$publishReleasePs1 = @'
# ==============================================================================
# HMS Automated Git Release & Build Script (publish_release.ps1)
# ==============================================================================

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -ErrorAction SilentlyContinue

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  🚀 HMS AUTOMATED GITHUB RELEASE & BUILD PUBLISHER" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Check if inside a Git repository
if (-not (Test-Path ".git")) {
    Write-Host "❌ Error: Not in a Git repository directory!" -ForegroundColor Red
    Write-Host "Please run this script from C:\github\projects\hook-management-system\" -ForegroundColor Yellow
    Exit 1
}

# 2. Extract current version from hms_master_gui.py
$detectedVersion = "v2.8.0"
if (Test-Path "hms_master_gui.py") {
    $match = Select-String -Path "hms_master_gui.py" -Pattern 'HMS_REV\s*=\s*"(v[^"]+)"'
    if ($match) {
        $detectedVersion =$match.Matches[0].Groups[1].Value
    }
}

Write-Host "`n🔍 Detected Version in hms_master_gui.py: " -NoNewline
Write-Host "$detectedVersion" -ForegroundColor Green

# 3. Prompt for Version Tag
$inputVersion = Read-Host "`nEnter release version tag (Press Enter for '$detectedVersion')"
if ([string]::IsNullOrWhitespace($inputVersion)) {
    $versionTag =$detectedVersion
} else {
    $versionTag =$inputVersion.Trim()
    if (-not $versionTag.StartsWith("v")) {
        $versionTag = "v" + $versionTag
    }
}

# 4. Prompt for Commit Message
$defaultCommit = "feat: release HMS $versionTag"
$inputCommit = Read-Host "Enter commit message (Press Enter for '$defaultCommit')"
if ([string]::IsNullOrWhitespace($inputCommit)) {
    $commitMsg =$defaultCommit
} else {
    $commitMsg =$inputCommit.Trim()
}

Write-Host "`n----------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "📌 Release Summary:" -ForegroundColor Yellow
Write-Host "   Version Tag    : $versionTag"
Write-Host "   Commit Message : $commitMsg"
Write-Host "----------------------------------------------------------------------" -ForegroundColor DarkGray

$confirm = Read-Host "`nProceed with git commit, push, and release tag? (Y/n)"
if ($confirm -and$confirm.Trim().ToLower() -ne "y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    Exit 0
}

# 5. Git Automation Steps
Write-Host "`n📦 [1/5] Staging files (git add .)..." -ForegroundColor Cyan
git add .

Write-Host "📝 [2/5] Committing changes..." -ForegroundColor Cyan
git commit -m "$commitMsg"

Write-Host "⬆️  [3/5] Pushing to main branch..." -ForegroundColor Cyan
git push origin main

# Delete tag locally/remotely if it already exists to allow re-tagging
git tag -d $versionTag 2>$null
git push origin --delete $versionTag 2>$null

Write-Host "🏷️  [4/5] Creating release tag $versionTag..." -ForegroundColor Cyan
git tag -a "$versionTag" -m "Release $versionTag"

Write-Host "🚀 [5/5] Pushing release tag to GitHub (triggers automated build)..." -ForegroundColor Cyan
git push origin "$versionTag"

Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host "  🎉 RELEASE $versionTag SUCCESSFULLY PUBLISHED TO GITHUB!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "GitHub Actions is now compiling 'hms_master_gui.exe' automatically." -ForegroundColor White
Write-Host "Check your repository's 'Actions' tab or 'Releases' page in a few minutes.`n" -ForegroundColor White
'@
Set-Content -Path "publish_release.ps1" -Value $publishReleasePs1 -Encoding UTF8

# 5. publish_release.bat
$publishReleaseBat = @'
@echo off
title HMS Release Publisher & GitHub Builder
powershell -ExecutionPolicy Bypass -File "%~dp0publish_release.ps1"
pause
'@
Set-Content -Path "publish_release.bat" -Value $publishReleaseBat -Encoding UTF8

# 6. requirements.txt
$requirementsTxt = @'
numpy>=1.24.0
librosa>=0.10.0
soundfile>=0.12.1
pyinstaller>=6.0.0
'@
Set-Content -Path "requirements.txt" -Value $requirementsTxt -Encoding UTF8

# 7. hms_master_gui.spec
$specContent = @'
# -*- mode: python ; coding: utf-8 -*-
import os

datas_list = [('337west_icon.ico', '.')] if os.path.exists('337west_icon.ico') else []
icon_file = ['337west_icon.ico'] if os.path.exists('337west_icon.ico') else None

a = Analysis(
    ['hms_master_gui.py'],
    pathex=[],
    binaries=[],
    datas=datas_list,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['setuptools'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='hms_master_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
'@
Set-Content -Path "hms_master_gui.spec" -Value $specContent -Encoding UTF8

# 8. Package into ZIP
$zipFile = Join-Path $RepoRoot "HMS_v2.8.0_Fixed.zip"
if (Test-Path $zipFile) { Remove-Item $zipFile -Force }

$filesToZip = @(
    "337west_icon.ico",
    "337west_icon.png",
    "build_exe.bat",
    "build_exe.py",
    "build_release.yml",
    ".github",
    "CHANGELOG.md",
    "davinci_import_sop.md",
    "hms_master_gui.py",
    "hms_master_gui.spec",
    "publish_release.bat",
    "publish_release.ps1",
    "README.md",
    "requirements.txt",
    "run_hms_track_pipeline.py",
    "trim_master_audio.py"
) | Where-Object { Test-Path $_ }

Compress-Archive -Path $filesToZip -DestinationPath $zipFile -Force
Write-Host "`nSUCCESS! Packaged all updated files into: $zipFile" -ForegroundColor Green
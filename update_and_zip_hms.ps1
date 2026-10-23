# ==============================================================================
# Script: update_and_zip_hms.ps1
# Version: 3.1
# Description: Packages Hook Management System v3.1 repository into a release ZIP.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$Version = "3.1",
    [string]$OutputDir = "release_payload"
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " HMS Release Packager v$Version | 337 West Productions" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 1. Enforce directory structure
$requiredDirs = @("output", "dist", $OutputDir, ".github\workflows")
foreach ($dir in $requiredDirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

# 2. Verify mandatory codebase assets
$criticalFiles = @(
    "hms_master_gui.py",
    "hms_v31_patcher.py",
    "hms_safety.py",
    "hms_manifest.py",
    "hms_metadata.py",
    "build_exe.py",
    "hms_master_gui.spec",
    "build_exe.bat",
    "publish_release.ps1",
    "publish_release.bat",
    ".github\workflows\build.yml",
    "README.md",
    "davinci_import_sop.md"
)

$missing = @()
foreach ($file in $criticalFiles) {
    if (-not (Test-Path $file)) {
        $missing += $file
    }
}

if ($missing.Count -gt 0) {
    Write-Host "[ERROR] Missing critical repository files:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

# 3. Stage files to payload directory
Write-Host "[STAGE] Preparing $OutputDir..." -ForegroundColor Cyan
Remove-Item -Path "$OutputDir\*" -Recurse -Force -ErrorAction SilentlyContinue

$stageFiles = @(
    $criticalFiles | Where-Object { $_ -ne ".github\workflows\build.yml" }
) + @("CHANGELOG.md", "update_and_zip_hms.ps1")
if (Test-Path "337west_icon.ico") {
    $stageFiles += "337west_icon.ico"
}

foreach ($item in $stageFiles) {
    if (Test-Path $item) {
        Copy-Item -Path $item -Destination $OutputDir -Force
    }
}

# Preserve GitHub Actions workflow hierarchy
$workflowTarget = Join-Path $OutputDir ".github\workflows"
New-Item -ItemType Directory -Path $workflowTarget -Force | Out-Null
Copy-Item ".github\workflows\build.yml" -Destination $workflowTarget -Force

# 4. Generate distribution archive
$zipName = "HMS_v$Version`_Release.zip"
$zipPath = Join-Path $ScriptDir $zipName

if (Test-Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}

Write-Host "[ZIP] Compressing into $zipName..." -ForegroundColor Cyan
Compress-Archive -Path "$OutputDir\*" -DestinationPath $zipPath -Force

$zipItem = Get-Item $zipPath
$zipSizeKB = [math]::Round($zipItem.Length / 1KB, 2)

Write-Host "[SUCCESS] Archive generated: $zipPath ($zipSizeKB KB)" -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan
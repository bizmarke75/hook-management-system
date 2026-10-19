# ==============================================================================
# Script: publish_release.ps1
# Version: 3.0.0
# Description: Automates git staging, commit, version tagging, and push to origin
#              to trigger the GitHub Actions CI/CD release build.
# ==============================================================================

[CmdletBinding()]
param(
    [string]$Tag = "v3.0.0",
    [string]$Message = "Release Hook Management System v3.0.0",
    [switch]$NonInteractive = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host " [HMS] AUTOMATED GITHUB RELEASE & BUILD PUBLISHER" -ForegroundColor Cyan
Write-Host " 337 West Productions | Lancaster, PA" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# Ensure git tracking is present
if (-not (Test-Path ".git")) {
    Write-Host "[ERROR] .git directory not found. Must run from repository root." -ForegroundColor Red
    exit 1
}

# Interactive configuration prompt
if (-not $NonInteractive) {
    $promptVersion = Read-Host "`nEnter release version tag [Press Enter for default: $Tag]"
    if (-not [string]::IsNullOrWhiteSpace($promptVersion)) {
        $Tag =$promptVersion.Trim()
    }

    $promptMsg = Read-Host "Enter release commit message [Press Enter for default: $Message]"
    if (-not [string]::IsNullOrWhiteSpace($promptMsg)) {
        $Message =$promptMsg.Trim()
    }

    Write-Host "`nRelease Plan:" -ForegroundColor Yellow
    Write-Host "  Version Tag    : $Tag" -ForegroundColor White
    Write-Host "  Commit Message : $Message" -ForegroundColor White

    $confirm = Read-Host "`nProceed with git commit, push, and release tag? (Y/n)"
    if ($confirm -match '^[Nn]') {
        Write-Host "[ABORT] Release cancelled by user." -ForegroundColor Yellow
        exit 0
    }
}

# 1. Stage changes
Write-Host "`n[GIT] Staging changes (git add -A)..." -ForegroundColor Cyan
git add -A

# 2. Commit modifications if working tree is dirty
Write-Host "[GIT] Committing changes..." -ForegroundColor Cyan
$status = git status --porcelain
if ($status) {
    git commit -m $Message
    Write-Host "[OK] Changes committed successfully." -ForegroundColor Green
} else {
    Write-Host "[INFO] No staged modifications to commit. Proceeding to tagging." -ForegroundColor Yellow
}

# 3. Apply annotated release tag
Write-Host "[GIT] Creating annotated tag: $Tag..." -ForegroundColor Cyan
git tag -a $Tag -m $Message -f

# 4. Push branch and tag to remote
Write-Host "[GIT] Pushing current branch to origin..." -ForegroundColor Cyan
git push origin HEAD

Write-Host "[GIT] Pushing release tag $Tag to origin..." -ForegroundColor Cyan
git push origin $Tag --force

Write-Host "`n======================================================================" -ForegroundColor Green
Write-Host " [SUCCESS] Release $Tag published successfully!" -ForegroundColor Green
Write-Host " GitHub Actions build triggered: .github/workflows/build_release.yml" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
# ==============================================================================
# HMS Automated Git Release & Build Script (publish_release.ps1)
# ==============================================================================

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -ErrorAction SilentlyContinue

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  HMS AUTOMATED GITHUB RELEASE & BUILD PUBLISHER [v2.8.0]" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# 1. Check if inside a Git repository
if (-not (Test-Path ".git")) {
    Write-Host "[ERROR] Not in a Git repository directory!" -ForegroundColor Red
    Write-Host "Please run this script from C:\github\projects\hook-management-system\" -ForegroundColor Yellow
    Exit 1
}

# 2. Extract current version from hms_master_gui.py
$detectedVersion = "v2.8.0"
if (Test-Path "hms_master_gui.py") {
    $match = Select-String -Path "hms_master_gui.py" -Pattern 'HMS_REV\s*=\s*"(v[^"]+)"'
    if ($match) {
        $detectedVersion = $match.Matches[0].Groups[1].Value
    }
}

Write-Host ""
Write-Host "Detected Version in hms_master_gui.py: " -NoNewline
Write-Host "$detectedVersion" -ForegroundColor Green
Write-Host ""

# 3. Prompt for Version Tag
Write-Host "Enter release version tag [Press Enter for $detectedVersion]: " -NoNewline -ForegroundColor Yellow
$inputVersion = Read-Host
if ([string]::IsNullOrWhitespace($inputVersion)) {
    $versionTag = $detectedVersion
} else {
    $versionTag = $inputVersion.Trim()
    if (-not $versionTag.StartsWith("v")) {
        $versionTag = "v" + $versionTag
    }
}

# 4. Prompt for Commit Message
$defaultCommit = "feat: release HMS $versionTag"
Write-Host "Enter commit message [Press Enter for '$defaultCommit']: " -NoNewline -ForegroundColor Yellow
$inputCommit = Read-Host
if ([string]::IsNullOrWhitespace($inputCommit)) {
    $commitMsg = $defaultCommit
} else {
    $commitMsg = $inputCommit.Trim()
}

Write-Host ""
Write-Host "----------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "Release Summary:" -ForegroundColor Yellow
Write-Host "   Version Tag    : $versionTag"
Write-Host "   Commit Message : $commitMsg"
Write-Host "----------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

Write-Host "Proceed with git commit, push, and release tag? (Y/n): " -NoNewline -ForegroundColor Yellow
$confirm = Read-Host
if ($confirm -and $confirm.Trim().ToLower() -ne "y") {
    Write-Host "Cancelled." -ForegroundColor Yellow
    Exit 0
}

# 5. Git Automation Steps
Write-Host ""
Write-Host "[1/5] Staging files (git add .)..." -ForegroundColor Cyan
git add .

Write-Host "[2/5] Committing changes..." -ForegroundColor Cyan
git commit -m "$commitMsg"

Write-Host "[3/5] Pushing to main branch..." -ForegroundColor Cyan
git push origin main

# Delete tag locally/remotely if it already exists to allow re-tagging
git tag -d $versionTag 2>$null
git push origin --delete $versionTag 2>$null

Write-Host "[4/5] Creating release tag $versionTag..." -ForegroundColor Cyan
git tag -a "$versionTag" -m "Release $versionTag"

Write-Host "[5/5] Pushing release tag to GitHub (triggers automated build)..." -ForegroundColor Cyan
git push origin "$versionTag"

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  RELEASE $versionTag SUCCESSFULLY PUBLISHED TO GITHUB!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "GitHub Actions is now compiling 'hms_master_gui.exe' automatically." -ForegroundColor White
Write-Host "Check your repository's 'Actions' tab or 'Releases' page in a few minutes." -ForegroundColor White
Write-Host ""

# Build dist\DupeSort-<version>-Windows-Setup.exe on Windows.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#
# Needs: Python 3.9+ with requirements.txt + pyinstaller installed, and Inno
# Setup 6 (https://jrsoftware.org/isdl.php). Pass -FetchHelpers to download
# fpcalc and FFmpeg into .\bin first so they are bundled with the app.
param([switch]$FetchHelpers, [string]$Python = "python")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if ($FetchHelpers) {
    New-Item -ItemType Directory -Force bin | Out-Null
    $tmp = Join-Path $env:TEMP ("dupesort-helpers-" + [guid]::NewGuid())
    New-Item -ItemType Directory $tmp | Out-Null
    # Chromaprint fpcalc (official release)
    Invoke-WebRequest "https://github.com/acoustid/chromaprint/releases/download/v1.5.1/chromaprint-fpcalc-1.5.1-windows-x86_64.zip" -OutFile "$tmp\fpcalc.zip"
    Expand-Archive "$tmp\fpcalc.zip" "$tmp\fpcalc"
    Copy-Item (Get-ChildItem "$tmp\fpcalc" -Recurse -Filter fpcalc.exe).FullName bin\
    # FFmpeg (BtbN builds, linked from ffmpeg.org); the GPL build includes x264 for H.264
    Invoke-WebRequest "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip" -OutFile "$tmp\ffmpeg.zip"
    Expand-Archive "$tmp\ffmpeg.zip" "$tmp\ffmpeg"
    $ffbin = (Get-ChildItem "$tmp\ffmpeg" -Recurse -Filter ffmpeg.exe).Directory.FullName
    Copy-Item "$ffbin\ffmpeg.exe", "$ffbin\ffprobe.exe", "$ffbin\*.dll" bin\
    Remove-Item -Recurse -Force $tmp
}

$version = & $Python -c "import dupesort; print(dupesort.__version__)"
if (-not (Test-Path packaging\icon.ico)) { & $Python packaging\make_icons.py }
& $Python -m PyInstaller --noconfirm dupesort.spec
if ($LASTEXITCODE) { throw "PyInstaller failed" }

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found - install it from https://jrsoftware.org/isdl.php" }
& $iscc "/DAppVersion=$version" packaging\windows\dupesort.iss
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Write-Host "Built dist\DupeSort-$version-Windows-Setup.exe"

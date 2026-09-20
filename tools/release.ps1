<#
.SYNOPSIS
  Build, package and (optionally) publish a release. Used by CI and by hand.

.DESCRIPTION
  Reads release.config.json in the project root. Steps:
    1. pre-build commands (icon, game data)
    2. PyInstaller
    3. sign the app            (only with -Sign, or when SIGN_PFX_BASE64 is set)
    4. Inno Setup installer
    5. sign the installer
    6. package into dist\release\ with FIXED file names so that
       https://github.com/<public repo>/releases/latest/download/<name> never changes:
         <AssetBase>-Setup.exe, <AssetBase>-Portable.zip, SHA256SUMS.txt
    7. with -Publish: create/update release v<version> on the PUBLIC repo using gh.
       Only binaries and notes are uploaded. Source code never leaves the private repo.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\release.ps1 -Sign -Publish      # full local release
  powershell -ExecutionPolicy Bypass -File tools\release.ps1 -SkipBuild -Publish # re-upload existing dist\
#>
[CmdletBinding()]
param(
    [switch]$Sign,
    [switch]$Publish,
    [switch]$SkipBuild,
    [switch]$Draft
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$cfg = Get-Content (Join-Path $root 'release.config.json') -Raw | ConvertFrom-Json

function Step($text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Run($exe, [string[]]$argv) {
    # Native tools write warnings to stderr; that must not abort the script under 'Stop'.
    $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    try { & $exe @argv } finally { $ErrorActionPreference = $prev }
    if ($LASTEXITCODE -ne 0) { throw "$exe $($argv -join ' ') failed with exit code $LASTEXITCODE" }
}

# Version comes from version_info.txt: filevers=(1, 0, 0, 0)
$vi = Get-Content (Join-Path $root 'version_info.txt') -Raw
if ($vi -notmatch 'filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)') { throw 'Could not read version from version_info.txt' }
$version = "$($Matches[1]).$($Matches[2]).$($Matches[3])"
$tag = "v$version"
Write-Host "$($cfg.appName) $tag"

$wantSign = $Sign -or [bool]$env:SIGN_PFX_BASE64
$appDir = Join-Path $root "dist\$($cfg.appName)"
$appExe = Join-Path $appDir "$($cfg.appName).exe"
$incFile = Join-Path $root 'installer\cert.iss.inc'

if (-not $SkipBuild) {
    Step 'Pre-build'
    $env:QT_QPA_PLATFORM = 'offscreen'          # icon generator uses Qt without a display
    foreach ($cmd in $cfg.preBuild) {
        $parts = $cmd -split ' '
        Run $parts[0] $parts[1..($parts.Length - 1)]
    }
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue

    Step 'PyInstaller'
    Run 'pyinstaller' @($cfg.spec, '--clean', '--noconfirm', '--log-level', 'WARN')

    if ($wantSign) {
        Step 'Sign app'
        Run 'powershell' @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'tools\sign.ps1', $appExe)
    } else {
        # An unsigned build must not offer to trust a certificate that did not sign it.
        if (Test-Path $incFile) { Set-Content -Path $incFile -Value "#define CertThumb `"`"`r`n#define CertSelfSigned 0`r`n" -Encoding ASCII -NoNewline }
        Write-Host 'Signing skipped (no -Sign and no SIGN_PFX_BASE64).'
    }

    Step 'Installer'
    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
              "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $iscc) { throw 'Inno Setup 6 not found. Install it with: winget install JRSoftware.InnoSetup' }
    Get-ChildItem (Join-Path $root 'dist\installer') -Filter '*.exe' -ErrorAction SilentlyContinue | ForEach-Object { [IO.File]::Delete($_.FullName) }
    Run $iscc @('/Q', 'installer\installer.iss')
}

$setup = Get-ChildItem (Join-Path $root 'dist\installer') -Filter "$($cfg.assetBase)-Setup-*.exe" | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $setup) { throw 'No installer found in dist\installer. Run without -SkipBuild.' }
if (-not (Test-Path $appExe)) { throw "App folder missing: $appDir" }

if ($wantSign -and -not $SkipBuild) {
    Step 'Sign installer'
    Run 'powershell' @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'tools\sign.ps1', $setup.FullName)
}

$rel = Join-Path $root 'dist\release'
$setupOut = Join-Path $rel "$($cfg.assetBase)-Setup.exe"
$zipOut = Join-Path $rel "$($cfg.assetBase)-Portable.zip"
# CI builds once, then calls this script again with -SkipBuild -Publish: do not zip 500 MB twice.
$reuse = $SkipBuild -and (Test-Path $setupOut) -and (Test-Path $zipOut) -and
         ((Get-Item $setupOut).LastWriteTime -ge $setup.LastWriteTime)
if ($reuse) {
    Step 'Package (reusing dist\release)'
} else {
    Step 'Package'
    if (Test-Path $rel) { Get-ChildItem $rel -File | ForEach-Object { [IO.File]::Delete($_.FullName) } } else { New-Item -ItemType Directory -Force $rel | Out-Null }
    Copy-Item $setup.FullName $setupOut
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    # includeBaseDirectory = true, so the zip unpacks to a single "<App Name>" folder
    [IO.Compression.ZipFile]::CreateFromDirectory($appDir, $zipOut, [IO.Compression.CompressionLevel]::Optimal, $true)
    $sums = foreach ($f in @($setupOut, $zipOut)) { "{0}  {1}" -f (Get-FileHash $f -Algorithm SHA256).Hash.ToLower(), (Split-Path -Leaf $f) }
    Set-Content -Path (Join-Path $rel 'SHA256SUMS.txt') -Value $sums -Encoding ASCII
}
Get-ChildItem $rel | ForEach-Object { "{0,-44} {1,8:N1} MB" -f $_.Name, ($_.Length / 1MB) }

$signed = [bool](Get-AuthenticodeSignature $setupOut).SignerCertificate
$notes = Join-Path $rel 'RELEASE_NOTES.md'
$changelog = Join-Path $root 'CHANGELOG.md'
$body = @("## $($cfg.appName) $version", '')
if (Test-Path $changelog) {
    $text = Get-Content $changelog -Raw
    if ($text -match "(?ms)^## \[?$([regex]::Escape($version))\]?.*?\r?\n(.*?)(?=^## |\z)") { $body += $Matches[1].Trim(); $body += '' }
}
$body += @(
    '### Download',
    "- **$($cfg.assetBase)-Setup.exe**: installer (Start Menu shortcut, uninstaller). Recommended.",
    "- **$($cfg.assetBase)-Portable.zip**: no install. Unzip anywhere and run ``$($cfg.appName).exe``.",
    '',
    'Windows 10/11, 64-bit. Your data stays on your PC.',
    '',
    $(if ($signed) { '> Signed with a self-signed Shadowskeep LLC certificate. Windows SmartScreen may still show "Windows protected your PC": choose **More info**, then **Run anyway**.' }
      else { '> This build is not code-signed. Windows SmartScreen will show "Windows protected your PC": choose **More info**, then **Run anyway**.' }),
    '',
    'Verify your download with `SHA256SUMS.txt`.',
    '',
    "If this saves you time, you can support development: $($cfg.supportUrl)"
)
Set-Content -Path $notes -Value $body -Encoding UTF8

if ($Publish) {
    Step "Publish $tag to $($cfg.publicRepo)"
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) not found.' }
    $assets = @($setupOut, $zipOut, (Join-Path $rel 'SHA256SUMS.txt'))
    $exists = $false
    try { gh release view $tag --repo $cfg.publicRepo *> $null; $exists = ($LASTEXITCODE -eq 0) } catch { $exists = $false }
    if ($exists) {
        Run 'gh' (@('release', 'upload', $tag, '--repo', $cfg.publicRepo, '--clobber') + $assets)
        Run 'gh' @('release', 'edit', $tag, '--repo', $cfg.publicRepo, '--notes-file', $notes)
    } else {
        $argv = @('release', 'create', $tag, '--repo', $cfg.publicRepo, '--title', "$($cfg.appName) $version", '--notes-file', $notes, '--latest')
        if ($Draft) { $argv += '--draft' }
        Run 'gh' ($argv + $assets)
    }
    Write-Host "Published: https://github.com/$($cfg.publicRepo)/releases/tag/$tag"
} else {
    Write-Host "`nPackaged only. Add -Publish to upload to $($cfg.publicRepo)."
}

<#
.SYNOPSIS
  Authenticode-sign one or more files for NMS Tracker.

.DESCRIPTION
  Looks for a code-signing certificate in this order:
    1. -Thumbprint (or env SHADOWSKEEP_SIGN_THUMBPRINT)  -> a purchased certificate in your store
    2. An existing self-signed cert with subject $Subject in Cert:\CurrentUser\My
    3. Creates a new self-signed cert (valid 5 years) and uses that

  SELF-SIGNED MEANS: the file carries a valid signature naming the publisher and
  proving it has not been modified, but Windows does not TRUST the publisher.
  SmartScreen and UAC will still say "Unknown publisher" on other PCs. Only a
  certificate bought from a certificate authority removes that warning. When you
  buy one, install it and pass its thumbprint; nothing else changes.

  The private key never leaves your Windows certificate store. The public
  certificate is exported to installer\ShadowskeepLLC-CodeSigning.cer.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\sign.ps1 "dist\NMS Tracker\NMS Tracker.exe"
#>
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Mandatory = $true, Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Files,
    [string]$Thumbprint = $env:SHADOWSKEEP_SIGN_THUMBPRINT,
    [string]$Subject = 'CN=Shadowskeep LLC, O=Shadowskeep LLC',
    [string]$TimestampServer = 'http://timestamp.digicert.com'
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Get-SigningCert {
    # CI: a code-signing .pfx supplied as a base64 secret is imported for this run only.
    if ($env:SIGN_PFX_BASE64) {
        $pfx = Join-Path ([IO.Path]::GetTempPath()) ("sign-" + [guid]::NewGuid().ToString('N') + '.pfx')
        [IO.File]::WriteAllBytes($pfx, [Convert]::FromBase64String($env:SIGN_PFX_BASE64))
        try {
            $pw = ConvertTo-SecureString -String ([string]$env:SIGN_PFX_PASSWORD) -AsPlainText -Force
            $c = Import-PfxCertificate -FilePath $pfx -CertStoreLocation Cert:\CurrentUser\My -Password $pw
        } finally { [IO.File]::Delete($pfx) }
        Write-Host "Using certificate from SIGN_PFX_BASE64: $($c.Subject)"
        return $c
    }
    if ($Thumbprint) {
        $c = Get-ChildItem Cert:\CurrentUser\My, Cert:\LocalMachine\My -ErrorAction SilentlyContinue |
            Where-Object { $_.Thumbprint -eq $Thumbprint } | Select-Object -First 1
        if (-not $c) { throw "No certificate with thumbprint $Thumbprint found." }
        Write-Host "Using certificate by thumbprint: $($c.Subject)"
        return $c
    }
    $c = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
        Where-Object { $_.Subject -eq $Subject -and $_.NotAfter -gt (Get-Date).AddDays(7) -and $_.HasPrivateKey } |
        Sort-Object NotAfter -Descending | Select-Object -First 1
    if ($c) {
        Write-Host "Using existing self-signed certificate (expires $($c.NotAfter.ToString('yyyy-MM-dd')))."
        return $c
    }
    Write-Host 'Creating a new self-signed code-signing certificate...'
    $c = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject `
        -FriendlyName 'Shadowskeep LLC Code Signing (self-signed)' `
        -KeyAlgorithm RSA -KeyLength 3072 -HashAlgorithm SHA256 `
        -KeyExportPolicy NonExportable -KeyUsage DigitalSignature `
        -CertStoreLocation Cert:\CurrentUser\My -NotAfter (Get-Date).AddYears(5)
    return $c
}

$cert = Get-SigningCert

# Export the PUBLIC certificate so it can be inspected or trusted on purpose.
$cerDir = Join-Path $root 'installer'
if (-not (Test-Path $cerDir)) { New-Item -ItemType Directory -Force $cerDir | Out-Null }
$cerPath = Join-Path $cerDir 'ShadowskeepLLC-CodeSigning.cer'
Export-Certificate -Cert $cert -FilePath $cerPath -Force | Out-Null
# Tell the installer script which certificate it may offer to trust (and remove on uninstall).
$selfSigned = if ($cert.Subject -eq $cert.Issuer) { 1 } else { 0 }
$inc = "#define CertThumb `"$($cert.Thumbprint)`"`r`n#define CertSelfSigned $selfSigned`r`n"
Set-Content -Path (Join-Path $cerDir 'cert.iss.inc') -Value $inc -Encoding ASCII -NoNewline

$failed = 0
foreach ($f in $Files) {
    if (-not (Test-Path $f)) { Write-Host "MISSING: $f"; $failed++; continue }
    $sig = $null
    try {
        $sig = Set-AuthenticodeSignature -FilePath $f -Certificate $cert -HashAlgorithm SHA256 `
            -TimestampServer $TimestampServer -ErrorAction Stop
    } catch {
        Write-Host "Timestamp server unavailable, signing without a timestamp: $($_.Exception.Message)"
        $sig = Set-AuthenticodeSignature -FilePath $f -Certificate $cert -HashAlgorithm SHA256
    }
    # With a self-signed cert the status is 'UnknownError' (untrusted root) even though
    # the signature itself was applied, so verify by the signer instead of the status.
    $check = Get-AuthenticodeSignature -FilePath $f
    if ($check.SignerCertificate -and $check.SignerCertificate.Thumbprint -eq $cert.Thumbprint) {
        $ts = if ($check.TimeStamperCertificate) { 'timestamped' } else { 'no timestamp' }
        Write-Host ("SIGNED  {0}  [{1}; trust status: {2}]" -f (Split-Path -Leaf $f), $ts, $check.Status)
    } else {
        Write-Host "FAILED  $f  ($($check.StatusMessage))"
        $failed++
    }
}
Write-Host "Certificate thumbprint: $($cert.Thumbprint)"
exit $failed

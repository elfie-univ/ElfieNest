<#!
Source-free Windows release bootstrap. It downloads one verified NSIS package and
uses the same canonical per-user application root as the manual installer.
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$NoLaunch,
    [string]$Manifest = "https://elfienest.com/releases/manifest.json",
    [switch]$Version
)

$ErrorActionPreference = "Stop"
$Target = "win32-x64"

if ($Version) {
    Write-Output "ElfieNest remote bootstrap 0.1.0-beta.1"
    exit 0
}
if (-not [Environment]::Is64BitOperatingSystem) {
    throw "unsupported-platform"
}

function Get-ManifestPayload([string]$Source) {
    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        return Get-Content -LiteralPath $Source -Raw | ConvertFrom-Json
    }
    if (-not $Source.StartsWith("https://")) {
        throw "manifest-url-must-use-https"
    }
    return (Invoke-WebRequest -UseBasicParsing -Uri $Source).Content | ConvertFrom-Json
}

$Payload = Get-ManifestPayload $Manifest
if ($Payload.schema_version -ne 1 -or -not $Payload.version) {
    throw "manifest-invalid"
}
$Artifact = @($Payload.artifacts | Where-Object { $_.target -eq $Target })
if ($Artifact.Count -ne 1 -or -not $Artifact[0].url -or -not $Artifact[0].sha256) {
    throw "manifest-invalid-or-target-missing"
}
$Artifact = $Artifact[0]
$ApplicationRoot = Join-Path $env:LOCALAPPDATA "Programs\ElfieNest"
Write-Output "target=$Target"
Write-Output "version=$($Payload.version)"
Write-Output "artifact_url=$($Artifact.url)"
Write-Output "application_root=$ApplicationRoot"
if ($DryRun) {
    exit 0
}
if (-not $Artifact.url.StartsWith("https://")) {
    throw "artifact-url-must-use-https"
}

$TemporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("elfienest-bootstrap-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $TemporaryRoot | Out-Null
try {
    $Installer = Join-Path $TemporaryRoot "ElfieNest.exe"
    Invoke-WebRequest -UseBasicParsing -Uri $Artifact.url -OutFile $Installer
    if ((Get-Item -LiteralPath $Installer).Length -ne [int64]$Artifact.size) {
        throw "artifact-size-mismatch"
    }
    if ((Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Artifact.sha256.ToLowerInvariant()) {
        throw "artifact-checksum-mismatch"
    }
    Start-Process -FilePath $Installer -ArgumentList "/S", "/D=$ApplicationRoot" -Wait -NoNewWindow
    $Cli = Join-Path $ApplicationRoot "resources\management-cli\ElfieNestCli.exe"
    $ManifestPath = Join-Path $ApplicationRoot "resources\manifest.json"
    if (-not (Test-Path -LiteralPath $Cli -PathType Leaf) -or -not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        throw "native-install-invalid"
    }
    $Bin = Join-Path $env:LOCALAPPDATA "ElfieNest\bin"
    New-Item -ItemType Directory -Force -Path $Bin | Out-Null
    Set-Content -LiteralPath (Join-Path $Bin "elfienest.cmd") -Value "@`"$Cli`" %*" -NoNewline
    if (-not $NoLaunch) {
        Start-Process -FilePath (Join-Path $ApplicationRoot "ElfieNest.exe")
    }
    Write-Output "remote-bootstrap-installed target=$Target version=$($Payload.version)"
}
finally {
    Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
}

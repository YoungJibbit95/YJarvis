[CmdletBinding()]
param([switch]$DryRun)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$setupRoot = Split-Path -Parent $PSScriptRoot
$setupTools = Join-Path $setupRoot '.setup-tools'

function Invoke-SetupCommand {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable fehlgeschlagen (Exitcode $LASTEXITCODE)."
    }
}

function Update-SetupPath {
    $setupPathEntries = ($env:Path + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')) -split ';'
    $env:Path = ($setupPathEntries | Where-Object { $_ } | Select-Object -Unique) -join ';'
}

function Install-SetupPackage {
    param([string]$Id)
    if (!(Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'WinGet fehlt. App Installer von Microsoft installieren, Terminal neu oeffnen und erneut starten: https://aka.ms/getwinget'
    }
    Write-Host "[setup] Installiere $Id"
    Invoke-SetupCommand winget.exe @('install', '--id', $Id, '--exact', '--source', 'winget', '--silent', '--accept-package-agreements', '--accept-source-agreements', '--disable-interactivity')
    Update-SetupPath
}

function Find-SetupPython {
    foreach ($candidate in @('py.exe', 'python3.11.exe', 'python.exe')) {
        if (!(Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
        $pythonArgs = @('-c', 'import sys; assert sys.version_info[:2] == (3, 11); print(sys.executable)')
        if ($candidate -eq 'py.exe') { $pythonArgs = @('-3.11') + $pythonArgs }
        # A missing version is expected during discovery, not a setup failure.
        try {
            $found = & $candidate @pythonArgs 2>$null
            if ($LASTEXITCODE -eq 0 -and $found -and (Test-Path -LiteralPath "$found" -PathType Leaf)) {
                return "$found"
            }
        } catch { continue }
    }
    return $null
}

function Get-SetupDownload {
    param([string]$Url, [string]$Destination, [string]$Sha256)
    Invoke-WebRequest -Uri $Url -OutFile $Destination -UseBasicParsing
    if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ne $Sha256) {
        throw "SHA256-Pruefung fehlgeschlagen: $Url"
    }
}

if ($DryRun) {
    Write-Host 'Windows x64: WinGet fuer fehlendes Git, Python 3.11, Ollama, FFmpeg und VC++ Runtime.'
    Write-Host 'Node 22 bei Bedarf lokal; whisper.cpp v1.8.3 CPU-CLI lokal. Downloads mit SHA256-Pruefung.'
    Write-Host 'Danach: .venv, beide requirements-Dateien, pip check, npm ci. Keine Modelle.'
    exit 0
}

$setupTemp = $null
try {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or
        [Environment]::GetEnvironmentVariable('PROCESSOR_ARCHITEW6432') -eq 'ARM64' -or
        $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
        throw 'Dieses Skript unterstuetzt Windows x64. Native 64-Bit-PowerShell verwenden.'
    }
    # The BAT bypass applies only to this process; no execution policy is persisted.
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Update-SetupPath
    foreach ($package in @(
        @{ Command = 'git.exe'; Id = 'Git.Git' },
        @{ Command = 'ollama.exe'; Id = 'Ollama.Ollama' },
        @{ Command = 'ffmpeg.exe'; Id = 'Gyan.FFmpeg' }
    )) {
        if (!(Get-Command $package.Command -ErrorAction SilentlyContinue)) {
            Install-SetupPackage $package.Id
        }
        if (!(Get-Command $package.Command -ErrorAction SilentlyContinue)) {
            throw "$($package.Command) fehlt im PATH. Terminal neu oeffnen und Setup wiederholen."
        }
    }
    $setupPython = Find-SetupPython
    if (!$setupPython) {
        Install-SetupPackage 'Python.Python.3.11'
        $setupPython = Find-SetupPython
    }
    if (!$setupPython) { throw 'Python 3.11 fehlt. Terminal neu oeffnen und Setup wiederholen.' }
    if (!(Test-Path -LiteralPath "$env:SystemRoot\System32\vcruntime140.dll") -or
        !(Test-Path -LiteralPath "$env:SystemRoot\System32\msvcp140.dll")) {
        Install-SetupPackage 'Microsoft.VCRedist.2015+.x64'
    }
    New-Item -ItemType Directory -Path $setupTools -Force | Out-Null
    $setupTemp = Join-Path ([IO.Path]::GetTempPath()) ('yjarvis-setup-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $setupTemp | Out-Null
    . (Join-Path $PSScriptRoot 'activate.ps1')

    $nodeVersion = ''
    if (Get-Command node.exe -ErrorAction SilentlyContinue) {
        $nodeVersion = & node.exe --version
        if ($LASTEXITCODE -ne 0) { throw 'Vorhandenes Node kann nicht gestartet werden.' }
    }
    if ($nodeVersion -notmatch '^v22\.' -or !(Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
        $nodeDestination = Join-Path $setupTools 'node'
        if (Test-Path -LiteralPath $nodeDestination) { throw "Lokales Node unvollstaendig/falsche Version: $nodeDestination" }
        $nodeArchive = Join-Path $setupTemp 'node.zip'
        Get-SetupDownload 'https://nodejs.org/dist/v22.23.3/node-v22.23.3-win-x64.zip' $nodeArchive '2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71'
        Expand-Archive -LiteralPath $nodeArchive -DestinationPath (Join-Path $setupTemp 'node')
        Copy-Item -LiteralPath (Join-Path $setupTemp 'node\node-v22.23.3-win-x64') -Destination $nodeDestination -Recurse
    }
    if (!(Get-Command whisper-cli.exe -ErrorAction SilentlyContinue)) {
        $whisperDestination = Join-Path $setupTools 'whisper'
        if (Test-Path -LiteralPath $whisperDestination) { throw "Lokales whisper.cpp unvollstaendig: $whisperDestination" }
        $whisperArchive = Join-Path $setupTemp 'whisper.zip'
        Get-SetupDownload 'https://github.com/ggml-org/whisper.cpp/releases/download/v1.8.3/whisper-bin-x64.zip' $whisperArchive 'd824b1e37599f882b396e73f1ee0bfd5d0529f700314c48311dcbd00b803321d'
        Expand-Archive -LiteralPath $whisperArchive -DestinationPath (Join-Path $setupTemp 'whisper')
        $whisperCli = @(Get-ChildItem -LiteralPath (Join-Path $setupTemp 'whisper') -Filter whisper-cli.exe -File -Recurse)
        if ($whisperCli.Count -ne 1) { throw 'whisper-cli.exe ist im Release-Archiv nicht eindeutig vorhanden.' }
        # Keep the DLLs alongside the executable.
        Copy-Item -LiteralPath $whisperCli[0].Directory.FullName -Destination $whisperDestination -Recurse
    }
    Invoke-SetupCommand node.exe @('--version')
    Invoke-SetupCommand ffmpeg.exe @('-version')
    Invoke-SetupCommand whisper-cli.exe @('--help')
    Invoke-SetupCommand $setupPython @((Join-Path $PSScriptRoot 'install_dependencies.py'))
    Write-Host '[setup] Fertig. Keine Modelle installiert. Neue PowerShell im Repo:'
    Write-Host 'powershell -NoProfile -ExecutionPolicy Bypass'
    Write-Host '. .\setup\activate.ps1'
    Write-Host '[setup] Modelle spaeter auswaehlen; Startbefehle stehen in setup/README.md.'
} catch {
    Write-Error "Setup fehlgeschlagen: $_" -ErrorAction Continue
    exit 1
} finally {
    if ($setupTemp -and (Test-Path -LiteralPath $setupTemp)) {
        # Only remove the exact directory created by this invocation under TEMP.
        $resolvedTemp = [IO.Path]::GetFullPath($setupTemp)
        $tempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
        if ([IO.Path]::GetDirectoryName($resolvedTemp) -eq $tempParent -and
            [IO.Path]::GetFileName($resolvedTemp) -like 'yjarvis-setup-*') {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
        }
    }
}

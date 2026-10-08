$ErrorActionPreference = 'Stop'
$installerRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$installerVersion = (Get-Content -LiteralPath (Join-Path $installerRoot 'apps\desktop\package.json') -Raw | ConvertFrom-Json).version
$installerFile = Join-Path $installerRoot "release\windows\YJarvis-$installerVersion-windows-x64-setup.exe"
$existingInstallation = @(
    Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue
    Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue
) | Where-Object { $_.DisplayName -like 'YJarvis*' }
if ($existingInstallation) { throw 'Existing YJarvis installation found; this smoke test will not replace it.' }
$installerTempParent = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\')
$installerTestDir = [IO.Path]::GetFullPath((Join-Path $installerTempParent ('yjarvis installer ' + [Guid]::NewGuid().ToString('N'))))
if ([IO.Path]::GetDirectoryName($installerTestDir) -ne $installerTempParent) { throw 'Invalid installer test directory' }
try {
    # NSIS /D must be last and unquoted, including when the target contains spaces.
    $installerProcess = Start-Process -FilePath $installerFile -ArgumentList ('/S /currentuser /D=' + $installerTestDir) -WindowStyle Hidden -Wait -PassThru
    if ($installerProcess.ExitCode -ne 0) { throw "Installer failed: $($installerProcess.ExitCode)" }
    foreach ($installedRelativePath in @('YJarvis.exe', 'resources\agent\jarvis-agent.exe', 'resources\app.asar')) {
        $installedFile = Join-Path $installerTestDir $installedRelativePath
        $unpackedFile = Join-Path $installerRoot ('release\windows\win-unpacked\' + $installedRelativePath)
        if (!(Test-Path -LiteralPath $installedFile -PathType Leaf)) { throw "Installed file missing: $installedRelativePath" }
        if ((Get-FileHash -LiteralPath $installedFile).Hash -ne (Get-FileHash -LiteralPath $unpackedFile).Hash) { throw "Installed file differs: $installedRelativePath" }
    }
    & node (Join-Path $installerRoot 'scripts\smoke-packaged-backend.mjs') (Join-Path $installerTestDir 'resources')
    if ($LASTEXITCODE -ne 0) { throw 'Installed backend smoke failed' }
    Write-Output 'NSIS install and installed-file integrity checks passed.'
} finally {
    $testUninstaller = Join-Path $installerTestDir 'Uninstall YJarvis.exe'
    if (Test-Path -LiteralPath $testUninstaller -PathType Leaf) {
        $uninstallProcess = Start-Process -FilePath $testUninstaller -ArgumentList '/S /currentuser' -WindowStyle Hidden -Wait -PassThru
        if ($uninstallProcess.ExitCode -ne 0) { throw "Test uninstaller failed: $($uninstallProcess.ExitCode)" }
        if (Test-Path -LiteralPath (Join-Path $installerTestDir 'YJarvis.exe')) { throw 'Test application remains after uninstall' }
        Write-Output 'NSIS uninstall passed; test application removed.'
    }
    # Delete only the unique test directory we created, after checking its parent.
    if (([IO.Path]::GetDirectoryName($installerTestDir) -eq $installerTempParent) -and
        ([IO.Path]::GetFileName($installerTestDir) -like 'yjarvis installer *') -and
        (Test-Path -LiteralPath $installerTestDir)) {
        Remove-Item -LiteralPath $installerTestDir -Recurse -Force
    }
}

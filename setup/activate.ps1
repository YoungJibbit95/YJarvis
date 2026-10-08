# Dot-source: . .\setup\activate.ps1
$setupRoot = Split-Path -Parent $PSScriptRoot
$setupPaths = @(
    (Join-Path $setupRoot '.venv\Scripts'),
    (Join-Path $setupRoot '.setup-tools\node'),
    (Join-Path $setupRoot '.setup-tools\whisper')
)
$env:Path = (($setupPaths + ($env:Path -split ';')) | Where-Object { $_ } | Select-Object -Unique) -join ';'
$env:JARVIS_PYTHON_BIN = Join-Path $setupRoot '.venv\Scripts\python.exe'

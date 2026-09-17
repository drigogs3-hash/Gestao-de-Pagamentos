$ErrorActionPreference='Stop'
Set-Location $PSScriptRoot
if (-not (Test-Path '.venv\Scripts\python.exe')) { py -3 -m venv .venv }
$py='.venv\Scripts\python.exe'
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements-dev.txt
& $py -m playwright install chromium
$env:PYTHONPATH=$PSScriptRoot
& $py -m compileall -q app.py core tests
& $py -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Testes automatizados falharam.' }
Write-Host 'Validacao funcional concluida.' -ForegroundColor Green

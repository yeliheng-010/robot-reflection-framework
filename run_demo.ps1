param(
    [ValidateSet('slip', 'success', 'persistent', 'missing')]
    [string]$Scenario = 'slip',
    [string]$PythonPath = ''
)
$ErrorActionPreference = 'Stop'
if (-not $PythonPath) {
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundledPython) {
        $PythonPath = $bundledPython
    } else {
        $PythonPath = (Get-Command python -ErrorAction Stop).Source
    }
}
Push-Location $PSScriptRoot
try {
    & $PythonPath -m reflection demo --scenario $Scenario
    if ($LASTEXITCODE -ne 0) { throw "Prototype exited with code $LASTEXITCODE" }
} finally {
    Pop-Location
}

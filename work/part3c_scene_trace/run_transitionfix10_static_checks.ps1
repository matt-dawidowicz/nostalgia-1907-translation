$ErrorActionPreference = "Stop"

$bundledPython = "C:\Users\thema\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path -LiteralPath $bundledPython) {
    $python = $bundledPython
} else {
    $pythonCommand = Get-Command python -ErrorAction Stop
    $python = $pythonCommand.Source
}

& $python (Join-Path $PSScriptRoot "verify_transitionfix10.py")
if ($LASTEXITCODE -ne 0) {
    throw "PART3C transitionfix10 static verification failed with exit code $LASTEXITCODE"
}

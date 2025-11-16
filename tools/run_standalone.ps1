# Create and activate a Python virtual environment, install requirements, and run main.py
# - Places where this script is located: tools/run_standalone.ps1
# - It expects the repository root to be the parent of the tools folder.
# Prerequisites: Python (3.x) available on PATH and permission to run scripts.

Set-StrictMode -Version Latest

$scriptDir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")

# Virtual environment path (inside repo root)
$venvDir = Join-Path $repoRoot ".venv"
$activateScript = Join-Path $venvDir "Scripts\Activate.ps1"

# Requirements file is in the tools folder
$requirementsFile = Join-Path $scriptDir "requirements.txt"

function Write-Info($msg) { Write-Host "[info] $msg" -ForegroundColor Cyan }
function Write-Err($msg) { Write-Host "[error] $msg" -ForegroundColor Red }

Write-Info "Repository root: $repoRoot"
Write-Info "Virtualenv path: $venvDir"
Write-Info "Requirements file: $requirementsFile"

# 1) Create virtual environment if missing
if (-Not (Test-Path $venvDir)) {
    Write-Info "Virtual environment not found. Creating: $venvDir"
    python -m venv "$venvDir"
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Failed to create virtual environment. Ensure 'python' is on PATH and supports venv."
        exit 1
    }
}

# 2) Ensure Activate script exists
if (-Not (Test-Path $activateScript)) {
    Write-Err "Activation script not found at: $activateScript"
    exit 1
}

# 3) Activate venv in current session
Write-Info "Activating virtual environment..."
# Dot-source the Activate.ps1 script to modify current session
. "$activateScript"

# 4) Install requirements
if (-Not (Test-Path $requirementsFile)) {
    Write-Err "requirements.txt file not found at: $requirementsFile"
    exit 1
}

Write-Info "Installing dependencies from requirements.txt..."
# Use pip from the venv explicitly
$pythonExe = Join-Path $venvDir "Scripts\python.exe"
if (-Not (Test-Path $pythonExe)) {
    Write-Err "Python executable not found in venv: $pythonExe"
    exit 1
}

& "$pythonExe" -m pip install --upgrade pip setuptools
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to upgrade pip/setuptools in virtual environment."
    exit 1
}

& "$pythonExe" -m pip install -r "$requirementsFile"
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to install dependencies from requirements.txt"
    exit 1
}

# 5) Run main.py from repository root
$guiPath = Join-Path $repoRoot "main.py"
if (-Not (Test-Path $guiPath)) {
    Write-Err "main.py not found at: $guiPath"
    exit 1
}

Write-Info "Launching GUI: $guiPath"
& "$pythonExe" "$guiPath"

# End
Write-Info "Process exited with code $LASTEXITCODE"
exit $LASTEXITCODE
# install_libs_requirements_uv.ps1
# ─────────────────────────────────────────────────────────────────────────────
# 1. Download and install uv (if not already on PATH).
# 2. Use uv to install Python 3.9 locally.
# 3. Create / recreate .venv with Python 3.9.
# 4. Install requirements into .\lib\  (portable bundle used by bootstrap).
#
# Location: tools/install_libs_requirements_uv.ps1
# Run from anywhere; the repo root is derived from script location.
# ─────────────────────────────────────────────────────────────────────────────
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDir        = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$repoRoot         = Resolve-Path (Join-Path $scriptDir "..")
$venvDir          = Join-Path $repoRoot ".venv"
$libDir           = Join-Path $repoRoot "lib"
$requirementsFile = Join-Path $scriptDir "requirements.txt"
$pythonExe        = Join-Path $venvDir "Scripts\python.exe"

function Write-Info($msg) { Write-Host "[info]  $msg" -ForegroundColor Cyan    }
function Write-Ok($msg)   { Write-Host "[ok]    $msg" -ForegroundColor Green   }
function Write-Err($msg)  { Write-Host "[error] $msg" -ForegroundColor Red     }

# ─── Step 1: Ensure uv is installed ────────────────────────────────────────
Write-Info "Checking for uv..."
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if (-Not $uvCmd) {
    Write-Info "uv not found on PATH. Downloading official installer..."
    try {
        # Official uv installer for Windows (PowerShell)
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    } catch {
        Write-Err "Could not auto-install uv: $_"
        Write-Err "Install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    }

    # Refresh the PATH so uv is discoverable in this session
    $machinePath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
    $userPath    = [System.Environment]::GetEnvironmentVariable("PATH", "User")
    $env:PATH    = "$machinePath;$userPath"

    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if (-Not $uvCmd) {
        Write-Err "uv still not on PATH after installation."
        Write-Err "Open a new shell and re-run this script."
        exit 1
    }
}
Write-Ok "uv: $(& uv --version)"

# ─── Step 2: Install Python 3.9 via uv ─────────────────────────────────────
Write-Info "Ensuring Python 3.9 is installed by uv..."
& uv python install 3.9
if ($LASTEXITCODE -ne 0) {
    Write-Err "uv failed to install Python 3.9 (exit $LASTEXITCODE)."
    exit 1
}
Write-Ok "Python 3.9 available."

# ─── Step 3: Create / verify .venv with Python 3.9 ─────────────────────────
$needNewVenv = $false

if (Test-Path $pythonExe) {
    # Check if the existing venv really is Python 3.9
    $verLine = & "$pythonExe" -c "import sys; print('{}.{}'.format(*sys.version_info[:2]))" 2>$null
    if ($verLine -ne '3.9') {
        Write-Info "Existing .venv uses Python $verLine — recreating for 3.9..."
        Remove-Item -Recurse -Force $venvDir
        $needNewVenv = $true
    } else {
        Write-Ok ".venv already uses Python 3.9."
    }
} else {
    $needNewVenv = $true
}

if ($needNewVenv) {
    Write-Info "Creating .venv with Python 3.9..."
    & uv venv --python 3.9 "$venvDir"
    if ($LASTEXITCODE -ne 0) {
        Write-Err "uv venv creation failed (exit $LASTEXITCODE)."
        exit 1
    }
    Write-Ok ".venv created at: $venvDir"
}

# ─── Step 4: Install packages into .\lib  (portable --target bundle) ────────
if (-Not (Test-Path $requirementsFile)) {
    Write-Err "requirements.txt not found: $requirementsFile"
    exit 1
}

Write-Info "Installing packages into: $libDir"
New-Item -ItemType Directory -Force -Path $libDir | Out-Null

# --target installs flat files into lib/ so dependency_bootstrap can add it
# to sys.path directly — no venv activation needed at runtime.
& uv pip install --python 3.9 --target "$libDir" -r "$requirementsFile"
if ($LASTEXITCODE -ne 0) {
    Write-Err "uv pip install --target lib/ failed (exit $LASTEXITCODE)."
    exit 1
}
Write-Ok "Packages installed into lib/."

# ─── Step 5: Also install into .venv for running main.py interactively ──────
Write-Info "Installing packages into .venv for interactive use..."
& uv pip install --python "$pythonExe" -r "$requirementsFile"
if ($LASTEXITCODE -ne 0) {
    Write-Info "venv install encountered issues; the app will fall back to lib/."
}

Write-Ok "All done."
Write-Info "To run the app:  .venv\Scripts\python.exe main.py"
exit 0


<#
.SYNOPSIS
  Build a portable StaX executable using cx_Freeze.

.DESCRIPTION
  Builds StaX into .\build\StaX-<version>\ using cx_Freeze.
  The uv virtual environment is synced automatically from pyproject.toml.
  The Nuke plugin files (nuke_launcher.py, menu.py, nuke_plugin\) are
  copied into the build so the installer can register them.

  Prerequisites
  -------------
  - uv          https://github.com/astral-sh/uv
  - cx_Freeze   listed as a dev/build dependency in pyproject.toml
  - PSWriteColor module in .\tools\modules\powershell\

  Flags
  -----
  --no-submodule-update   Skip 'git submodule update --init --recursive'

.EXAMPLE
  PS> .\tools\build.ps1

.EXAMPLE
  PS> .\tools\build.ps1 --no-submodule-update

.LINK
  https://aramadan0096.github.io/stax-docs/
#>

param([switch]$NoSubmoduleUpdate)
if ($args -contains "--no-submodule-update") { $NoSubmoduleUpdate = $true }

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$script_dir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$stax_root  = (Get-Item $script_dir).Parent.FullName
$current_dir = Get-Location

$env:PSModulePath = $env:PSModulePath + ";$stax_root\tools\modules\powershell"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Exit-WithCode([int]$code) {
    $parentPID      = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$PID" |
                       Select-Object -Property ParentProcessId).ParentProcessId
    $parentProcName = (Get-CimInstance -ClassName Win32_Process -Filter "ProcessId=$parentPID" |
                       Select-Object -Property Name).Name
    if ('powershell.exe' -eq $parentProcName) { $host.SetShouldExit($code) }
    exit $code
}

function Require-Command([string]$cmd, [string]$hint) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        Write-Color -Text "!!! ", "Required command not found: ", $cmd `
                    -Color Red, Yellow, White
        if ($hint) { Write-Color -Text "    ", $hint -Color Gray, White }
        Exit-WithCode 1
    }
}

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
$art = @"

  ____  _         __  __
 / ___|| |_ __ _  \ \/ /
 \___ \| __/ _' |  \  /
  ___) | || (_| |  /  \
 |____/ \__\__,_| /_/\_\

         Build System  —  cx_Freeze portable build

"@
Write-Host $art -ForegroundColor DarkCyan

if ($PSVersionTable.PSVersion.Major -lt 7) {
    Write-Color -Text "*** ", "PowerShell 7+ recommended. " `
                      "https://github.com/PowerShell/PowerShell/releases" `
                -Color Yellow, Gray
}

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------
Require-Command "uv"  "Install uv: https://github.com/astral-sh/uv#installation"
Require-Command "git" "Install Git: https://git-scm.com"

# ---------------------------------------------------------------------------
# Resolve StaX version
# ---------------------------------------------------------------------------
$stax_version = $null

foreach ($vf in @("$stax_root\main.py", "$stax_root\src\version.py")) {
    if (Test-Path $vf) {
        $m = [regex]::Match((Get-Content -Raw $vf), '__version__\s*=\s*"(?<v>[^"]+)"')
        if ($m.Success) { $stax_version = $m.Groups['v'].Value; break }
    }
}
if (-not $stax_version -and (Test-Path "$stax_root\pyproject.toml")) {
    $m = [regex]::Match((Get-Content -Raw "$stax_root\pyproject.toml"), 'version\s*=\s*"(?<v>[^"]+)"')
    if ($m.Success) { $stax_version = $m.Groups['v'].Value }
}
if (-not $stax_version) {
    Write-Color -Text "!!! ", "Cannot determine StaX version." -Color Red, Yellow
    Exit-WithCode 1
}
Write-Color -Text ">>> ", "StaX version: ", $stax_version -Color Green, Gray, Cyan

# ---------------------------------------------------------------------------
# Submodule update
# ---------------------------------------------------------------------------
if (-not $NoSubmoduleUpdate) {
    Write-Color -Text ">>> ", "Updating submodules ..." -Color Green, Gray
    & git -C $stax_root submodule update --init --recursive
    if ($LASTEXITCODE -ne 0) {
        Write-Color -Text "!!! ", "git submodule update failed." -Color Red, Yellow
        Exit-WithCode $LASTEXITCODE
    }
} else {
    Write-Color -Text "*** ", "Skipping submodule update." -Color Yellow, Gray
}

# ---------------------------------------------------------------------------
# uv sync — create / update .venv from pyproject.toml
# ---------------------------------------------------------------------------
Write-Color -Text ">>> ", "Syncing uv environment ..." -Color Green, Gray
Push-Location $stax_root
& uv sync --all-extras
if ($LASTEXITCODE -ne 0) {
    Write-Color -Text "!!! ", "'uv sync' failed — check pyproject.toml." -Color Red, Yellow
    Pop-Location
    Exit-WithCode $LASTEXITCODE
}
Pop-Location

# Locate Python inside the uv venv
$venv_python = "$stax_root\.venv\Scripts\python.exe"
if (-not (Test-Path $venv_python)) {
    # Fallback: lib folder with a bundled Python
    $venv_python = "$stax_root\lib\python.exe"
}
if (-not (Test-Path $venv_python)) {
    Write-Color -Text "!!! ", "Python interpreter not found in .venv or lib." `
                -Color Red, Yellow
    Exit-WithCode 1
}
Write-Color -Text "--- ", "Python:     ", $venv_python -Color Gray, Gray, White

# Verify cx_Freeze
$cx_ver = & $venv_python -c "import cx_Freeze; print(cx_Freeze.__version__)" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Color -Text "!!! ", "cx_Freeze not found in venv. Add it:" -Color Red, Yellow
    Write-Color -Text '    uv add "cx-freeze" --dev' -Color White
    Exit-WithCode 1
}
Write-Color -Text "--- ", "cx_Freeze:  ", $cx_ver -Color Gray, Gray, White

# ---------------------------------------------------------------------------
# Prepare build directories
# ---------------------------------------------------------------------------
$build_root = "$stax_root\build"
$build_out  = "$build_root\StaX-$stax_version"
$log_file   = "$build_root\build.log"

if (-not (Test-Path $build_root)) {
    New-Item -ItemType Directory -Force -Path $build_root | Out-Null
}

Write-Color -Text "--- ", "Cleaning previous build output ..." -Color Yellow, Gray
try {
    if (Test-Path $build_out) { Remove-Item -Recurse -Force $build_out }
} catch {
    Write-Color -Text "!!! ", "Cannot clean build directory — close any open handles." `
                -Color Red, Yellow
    Write-Color -Text $_.Exception.Message -Color Red
    Exit-WithCode 1
}
New-Item -ItemType Directory -Force -Path $build_out | Out-Null

# ---------------------------------------------------------------------------
# Clean Python cache
# ---------------------------------------------------------------------------
Write-Color -Text ">>> ", "Removing .pyc / __pycache__ ..." -Color Green, Gray -NoNewline
Get-ChildItem $stax_root -Filter "*.pyc"       -Force -Recurse |
    Where-Object { $_.FullName -inotmatch 'build' } | Remove-Item -Force
Get-ChildItem $stax_root -Filter "*.pyo"       -Force -Recurse |
    Where-Object { $_.FullName -inotmatch 'build' } | Remove-Item -Force
Get-ChildItem $stax_root -Filter "__pycache__" -Force -Recurse |
    Where-Object { $_.FullName -inotmatch 'build' } | Remove-Item -Force -Recurse
Write-Color -Text "OK" -Color Green

# ---------------------------------------------------------------------------
# Run cx_Freeze via setup_freeze.py
# STAX_BUILD_OUT tells setup_freeze.py exactly where to put the output.
# ---------------------------------------------------------------------------
$env:STAX_BUILD_OUT = $build_out

$setup_freeze = "$stax_root\setup_freeze.py"
if (-not (Test-Path $setup_freeze)) {
    Write-Color -Text "!!! ", "setup_freeze.py not found at repo root." -Color Red, Yellow
    Write-Color -Text "    Expected: ", $setup_freeze -Color Gray, White
    Exit-WithCode 1
}

Write-Color -Text ">>> ", "Building StaX with cx_Freeze ..." -Color Green, White
$startTime = [int][double]::Parse((Get-Date -UFormat %s))

Set-Location -Path $stax_root
$out = & $venv_python $setup_freeze build_exe 2>&1
Set-Content -Path $log_file -Value $out -Encoding UTF8

if ($LASTEXITCODE -ne 0) {
    Write-Color -Text "------------------------------------------" -Color Red
    Get-Content $log_file | Select-Object -Last 50
    Write-Color -Text "------------------------------------------" -Color Yellow
    Write-Color -Text "!!! ", "Build FAILED. Full log: ", ".\build\build.log" `
                -Color Red, Yellow, White
    Set-Location -Path $current_dir
    Exit-WithCode $LASTEXITCODE
}

# ---------------------------------------------------------------------------
# Post-build: copy Nuke plugin files into the build tree
# (setup_freeze.py already does this via include_files, but we also write
#  the init snippet and VERSION here as belt-and-suspenders.)
# ---------------------------------------------------------------------------
Write-Color -Text ">>> ", "Finalising Nuke plugin assets ..." -Color Green, Gray

# Write the init snippet (used by the installer's Pascal code)
$nuke_init_snippet = @"
# StaX — auto-generated by installer
# Append this block to %USERPROFILE%\.nuke\init.py
# or let the StaX installer do it automatically.
import sys, os as _os
_stax_nuke = _os.path.join(_os.path.dirname(__file__), "nuke_plugin")
if _stax_nuke not in sys.path:
    sys.path.insert(0, _stax_nuke)
"@
Set-Content -Path "$build_out\nuke_init_snippet.py" -Value $nuke_init_snippet -Encoding UTF8
Write-Color -Text "    ", "Written: nuke_init_snippet.py" -Color Gray, White

# Write VERSION file (installer reads this without importing Python)
Set-Content -Path "$build_out\VERSION" -Value $stax_version -Encoding UTF8
Write-Color -Text "    ", "Written: VERSION ($stax_version)" -Color Gray, White

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
$endTime = [int][double]::Parse((Get-Date -UFormat %s))
$elapsed = $endTime - $startTime

Set-Location -Path $current_dir

try {
    New-BurntToastNotification `
        -AppLogo "$stax_root\resources\logo.png" `
        -Text    "StaX build complete!", "Done in $elapsed sec — .\build\StaX-$stax_version" `
        -ErrorAction SilentlyContinue
} catch {}

Write-Color -Text ""
Write-Color -Text "*** ", "Build complete in ", "$elapsed", " sec." `
            -Color Green, Gray, White, Gray
Write-Color -Text "*** ", "Portable build:  ", ".\build\StaX-$stax_version\" `
            -Color Green, Gray, White
Write-Color -Text "*** ", "Build log:        ", ".\build\build.log" `
            -Color Green, Gray, White
Write-Color -Text ""
Write-Color -Text "    Run ", ".\tools\build_win_installer.ps1", " to create an installer." `
            -Color Gray, Cyan, Gray
            
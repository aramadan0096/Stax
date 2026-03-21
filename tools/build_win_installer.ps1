<#
.SYNOPSIS
  Build a Windows installer for StaX from the cx_Freeze portable build.

.DESCRIPTION
  Takes the output of .\tools\build.ps1 (located in .\build\StaX-<version>\)
  and produces a single-file Windows installer EXE using Inno Setup 6.

  What the installer does
  -----------------------
  1. Installs the portable StaX build to %ProgramFiles%\StaX\
  2. Creates a Desktop shortcut and Start Menu entry for StaX.exe
  3. Copies the Nuke plugin folder to the install directory.
  4. Optionally appends the StaX init snippet to the user's
     %USERPROFILE%\.nuke\init.py (user opts in via installer checkbox).
  5. Creates an Uninstall entry in Add/Remove Programs.

  Prerequisites
  -------------
  - Inno Setup 6   (https://jrsoftware.org/isinfo.php)
    Either on PATH as `iscc` or at the standard install location
    C:\Program Files (x86)\Inno Setup 6\ISCC.exe
  - .\tools\build.ps1 must have been run first (.\build\StaX-<version>\ exists)
  - PSWriteColor module present in .\tools\modules\powershell\

.EXAMPLE
  PS> .\tools\build_win_installer.ps1

.EXAMPLE
  Build everything in one go:
  PS> .\tools\build.ps1 ; .\tools\build_win_installer.ps1

.LINK
  https://aramadan0096.github.io/stax-docs/
#>

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------
$script_dir = Split-Path -Path $MyInvocation.MyCommand.Definition -Parent
$stax_root  = (Get-Item $script_dir).Parent.FullName

# PSWriteColor
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
        Write-Color -Text "!!! ", "Required command not found: ", $cmd -Color Red, Yellow, White
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

         Build System  —  Windows Installer (Inno Setup)

"@
Write-Host $art -ForegroundColor DarkCyan

# ---------------------------------------------------------------------------
# Resolve StaX version
# ---------------------------------------------------------------------------
$stax_version = $null

# 1. Try the VERSION file written by build.ps1 (most reliable)
$build_root = "$stax_root\build"
$version_sentinel = Get-ChildItem -Path $build_root -Filter "VERSION" -Recurse `
                    -ErrorAction SilentlyContinue | Select-Object -First 1
if ($version_sentinel) {
    $stax_version = (Get-Content $version_sentinel.FullName -Raw).Trim()
}

# 2. Fallback: parse main.py / pyproject.toml
if (-not $stax_version) {
    foreach ($vf in @("$stax_root\main.py", "$stax_root\src\version.py")) {
        if (Test-Path $vf) {
            $m = [regex]::Match((Get-Content -Raw $vf), '__version__\s*=\s*"(?<v>[^"]+)"')
            if ($m.Success) { $stax_version = $m.Groups['v'].Value; break }
        }
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
$env:STAX_VERSION = $stax_version

# ---------------------------------------------------------------------------
# Verify the portable build exists
# ---------------------------------------------------------------------------
$build_dir = "$build_root\StaX-$stax_version"

if (-not (Test-Path $build_dir)) {
    Write-Color -Text "!!! ", "Portable build not found at: ", $build_dir `
                -Color Red, Yellow, White
    Write-Color -Text "    Run ", ".\tools\build.ps1", " first." -Color Gray, Cyan, Gray
    Exit-WithCode 1
}
Write-Color -Text "--- ", "Build directory: ", $build_dir -Color Gray, Gray, White
$env:STAX_BUILD_DIR = $build_dir

# ---------------------------------------------------------------------------
# Locate Inno Setup (iscc)
# ---------------------------------------------------------------------------
$iscc = $null

# Check PATH first
if (Get-Command "iscc" -ErrorAction SilentlyContinue) {
    $iscc = "iscc"
}

# Standard install locations
if (-not $iscc) {
    $candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 5\ISCC.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { $iscc = $c; break }
    }
}

if (-not $iscc) {
    Write-Color -Text "!!! ", "Inno Setup (iscc) not found." -Color Red, Yellow
    Write-Color -Text "    Download: ", "https://jrsoftware.org/isinfo.php" `
                -Color Gray, White
    Exit-WithCode 1
}
Write-Color -Text "--- ", "Inno Setup: ", $iscc -Color Gray, Gray, White

# ---------------------------------------------------------------------------
# Ensure output directory for the installer EXE exists
# ---------------------------------------------------------------------------
$installer_out = "$build_root\installer"
if (-not (Test-Path $installer_out)) {
    New-Item -ItemType Directory -Force -Path $installer_out | Out-Null
}
$env:STAX_INSTALLER_OUT = $installer_out

# ---------------------------------------------------------------------------
# Generate the Inno Setup script on the fly
# This means we never need a committed .iss file and the paths are always
# correct for the current machine and version.
# ---------------------------------------------------------------------------
$iss_path = "$stax_root\tools\_stax_installer_tmp.iss"

# Nuke plugin path inside the build
$nuke_plugin_in_build = "$build_dir\nuke_plugin"
$has_nuke_plugin = Test-Path $nuke_plugin_in_build

# Conditionally include Nuke plugin section
$nuke_plugin_section = ""
if ($has_nuke_plugin) {
    $nuke_plugin_section = @"

; ---- Nuke plugin (optional component) ----
Source: "$($nuke_plugin_in_build -replace '\\', '\\')\*"; DestDir: "{app}\nuke_plugin"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: nukeplugin
"@
}

$nuke_component_entry = ""
$nuke_tasks_entry = ""
if ($has_nuke_plugin) {
    $nuke_component_entry = @"

Name: "nukeplugin"; Description: "Nuke Plugin (registers StaX in Foundry Nuke)"; Types: full; Flags: checkablealone
"@
    $nuke_tasks_entry = @"

Name: "nuke_init"; Description: "Append StaX loader to %USERPROFILE%\.nuke\init.py"; GroupDescription: "Nuke Integration:"; Components: nukeplugin
"@
}

$iss_content = @"
; ===========================================================================
; StaX Windows Installer
; Auto-generated by tools\build_win_installer.ps1 — do not edit manually.
; ===========================================================================

#define AppName      "StaX"
#define AppVersion   "$stax_version"
#define AppPublisher "Ahmed Ramadan"
#define AppURL       "https://aramadan0096.github.io/stax-docs/"
#define AppExeName   "StaX.exe"
#define BuildDir     "$($build_dir -replace '\\', '\\')"
#define OutputDir    "$($installer_out -replace '\\', '\\')"
#define AppIcon      "$($stax_root -replace '\\', '\\')\resources\logo.png"

[Setup]
AppId                    = {{A8F3C2D1-4B7E-4F9A-B6C0-2E1D5A8F3C2D}}
AppName                  = {#AppName}
AppVersion               = {#AppVersion}
AppVerName               = {#AppName} {#AppVersion}
AppPublisher             = {#AppPublisher}
AppPublisherURL          = {#AppURL}
AppSupportURL            = {#AppURL}
AppUpdatesURL            = {#AppURL}
DefaultDirName           = {autopf}\{#AppName}
DefaultGroupName         = {#AppName}
AllowNoIcons             = yes
OutputDir                = {#OutputDir}
OutputBaseFilename       = StaX-{#AppVersion}-win64-setup
Compression              = lzma2/ultra64
SolidCompression         = yes
WizardStyle              = modern
ArchitecturesInstallIn64BitMode = x64
ArchitecturesAllowed     = x64
PrivilegesRequired       = admin
SetupIconFile            = {#AppIcon}
UninstallDisplayIcon     = {app}\{#AppExeName}
VersionInfoVersion       = {#AppVersion}
VersionInfoProductName   = {#AppName}
VersionInfoCompany       = {#AppPublisher}
; Minimum Windows 10
MinVersion               = 10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full";    Description: "Full installation"
Name: "compact"; Description: "Compact installation (no Nuke plugin)"
Name: "custom";  Description: "Custom installation"; Flags: iscustom

[Components]
Name: "main";    Description: "StaX core application"; Types: full compact custom; Flags: fixed
$nuke_component_entry

[Tasks]
Name: "desktopicon";  Description: "Create a &Desktop shortcut";         GroupDescription: "Additional shortcuts:"
Name: "startmenu";    Description: "Create a &Start Menu entry";          GroupDescription: "Additional shortcuts:"; Flags: checkedonce
$nuke_tasks_entry

[Files]
; ---- Core application ----
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Components: main
$nuke_plugin_section

[Icons]
; Desktop shortcut
Name: "{autodesktop}\{#AppName}";            Filename: "{app}\{#AppExeName}"; Tasks: desktopicon
; Start Menu
Name: "{group}\{#AppName}";                  Filename: "{app}\{#AppExeName}"; Tasks: startmenu
Name: "{group}\{#AppName} Documentation";    Filename: "{#AppURL}";            Tasks: startmenu
Name: "{group}\Uninstall {#AppName}";        Filename: "{uninstallexe}";       Tasks: startmenu

[Run]
; Launch StaX after install
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[Code]
// ---------------------------------------------------------------------------
// Nuke init.py integration (runs only when task 'nuke_init' is selected)
// ---------------------------------------------------------------------------

const
  NukeInitSnippetMarker = '# StaX — auto-generated by installer';

function GetNukeInitPath(): String;
begin
  Result := ExpandConstant('{%USERPROFILE}') + '\.nuke\init.py';
end;

procedure AppendStaXToNukeInit();
var
  NukeInitPath  : String;
  NukeInitDir   : String;
  SnippetFile   : String;
  ExistingText  : TArrayOfString;
  NewLine       : String;
  SnippetLines  : TArrayOfString;
  Combined      : TArrayOfString;
  I             : Integer;
begin
  if not WizardIsTaskSelected('nuke_init') then Exit;

  NukeInitPath := GetNukeInitPath();
  NukeInitDir  := ExtractFilePath(NukeInitPath);
  SnippetFile  := ExpandConstant('{app}') + '\nuke_init_snippet.py';

  // Create .nuke dir if it doesn't exist
  if not DirExists(NukeInitDir) then
    ForceDirectories(NukeInitDir);

  // Read snippet
  if not LoadStringsFromFile(SnippetFile, SnippetLines) then
  begin
    MsgBox('Could not read Nuke init snippet from: ' + SnippetFile, mbError, MB_OK);
    Exit;
  end;

  // Check if already present
  if FileExists(NukeInitPath) then
  begin
    LoadStringsFromFile(NukeInitPath, ExistingText);
    for I := 0 to GetArrayLength(ExistingText) - 1 do
    begin
      if Pos(NukeInitSnippetMarker, ExistingText[I]) > 0 then
      begin
        // Already installed — skip silently
        Exit;
      end;
    end;

    // Append to existing file
    SetArrayLength(Combined, GetArrayLength(ExistingText) + 1 + GetArrayLength(SnippetLines));
    for I := 0 to GetArrayLength(ExistingText) - 1 do
      Combined[I] := ExistingText[I];
    Combined[GetArrayLength(ExistingText)] := '';  // blank separator line
    for I := 0 to GetArrayLength(SnippetLines) - 1 do
      Combined[GetArrayLength(ExistingText) + 1 + I] := SnippetLines[I];
    SaveStringsToFile(NukeInitPath, Combined, False);
  end
  else
  begin
    // Create fresh init.py
    SaveStringsToFile(NukeInitPath, SnippetLines, False);
  end;
end;

procedure RemoveStaXFromNukeInit();
var
  NukeInitPath  : String;
  ExistingText  : TArrayOfString;
  Filtered      : TArrayOfString;
  I, J          : Integer;
  InBlock       : Boolean;
begin
  NukeInitPath := GetNukeInitPath();
  if not FileExists(NukeInitPath) then Exit;

  LoadStringsFromFile(NukeInitPath, ExistingText);
  SetArrayLength(Filtered, 0);
  InBlock := False;
  J := 0;

  for I := 0 to GetArrayLength(ExistingText) - 1 do
  begin
    if Pos(NukeInitSnippetMarker, ExistingText[I]) > 0 then
    begin
      InBlock := True;
    end;

    if not InBlock then
    begin
      SetArrayLength(Filtered, J + 1);
      Filtered[J] := ExistingText[I];
      J := J + 1;
    end;

    // The StaX block ends after the last line of the snippet (heuristic: blank line after block)
    if InBlock and (ExistingText[I] = '') then
      InBlock := False;
  end;

  SaveStringsToFile(NukeInitPath, Filtered, False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    AppendStaXToNukeInit();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveStaXFromNukeInit();
end;
"@

Set-Content -Path $iss_path -Value $iss_content -Encoding UTF8
Write-Color -Text "--- ", "Inno Setup script written to ", "_stax_installer_tmp.iss" `
            -Color Gray, Gray, White

# ---------------------------------------------------------------------------
# Run Inno Setup
# ---------------------------------------------------------------------------
Write-Color -Text ">>> ", "Compiling installer ..." -Color Green, White

$startTime = [int][double]::Parse((Get-Date -UFormat %s))

& $iscc $iss_path
$iss_exit = $LASTEXITCODE

Remove-Item $iss_path -Force -ErrorAction SilentlyContinue

if ($iss_exit -ne 0) {
    Write-Color -Text "!!! ", "Inno Setup compilation failed (exit $iss_exit)." `
                -Color Red, Yellow
    Exit-WithCode $iss_exit
}

$endTime = [int][double]::Parse((Get-Date -UFormat %s))
$elapsed = $endTime - $startTime

# ---------------------------------------------------------------------------
# Locate the produced installer file
# ---------------------------------------------------------------------------
$installer_exe = Get-ChildItem -Path $installer_out -Filter "StaX-$stax_version-win64-setup.exe" |
                 Select-Object -First 1

try {
    New-BurntToastNotification `
        -AppLogo "$stax_root\resources\logo.png" `
        -Text    "StaX installer ready!", "Done in $elapsed sec — .\build\installer\" `
        -ErrorAction SilentlyContinue
} catch {}

Write-Color -Text ""
Write-Color -Text "*** ", "Installer ready in ", "$elapsed", " sec." `
            -Color Green, Gray, White, Gray
if ($installer_exe) {
    Write-Color -Text "*** ", "File: ", ".\build\installer\$($installer_exe.Name)" `
                -Color Green, Gray, White
} else {
    Write-Color -Text "*** ", "Output: ", ".\build\installer\" -Color Green, Gray, White
}
Write-Color -Text ""

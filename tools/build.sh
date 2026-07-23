#!/usr/bin/env bash
# Build a portable StaX with cx_Freeze on Linux.
# Mirrors tools/build.ps1 essentials. Full native installer (AppImage/.deb)
# is a documented follow-up.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
stax_root="$(dirname "$script_dir")"
cd "$stax_root"

command -v uv >/dev/null 2>&1 || { echo "uv not found: https://github.com/astral-sh/uv"; exit 1; }

if command -v python3 >/dev/null 2>&1; then
	py_cmd="python3"
elif command -v python >/dev/null 2>&1; then
	py_cmd="python"
else
	echo "python3/python not found" >&2
	exit 1
fi

if [ ! -f "src/version.py" ]; then
	echo "src/version.py not found" >&2
	exit 1
fi

# Single-sourced version from src/version.py
version="$($py_cmd - <<'PY'
import io
import re

m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', io.open("src/version.py", encoding="utf-8").read())
print(m.group(1) if m else "0.0.0")
PY
)"

if [ "$version" = "0.0.0" ]; then
	echo "unable to parse version from src/version.py" >&2
	exit 1
fi

echo ">>> StaX version: $version"

echo ">>> Syncing uv environment ..."
uv sync --all-extras

python_bin="$stax_root/.venv/bin/python"
if [ ! -x "$python_bin" ]; then
	echo "missing Python interpreter in .venv: $python_bin" >&2
	exit 1
fi

build_out="$stax_root/build/StaX-$version"
rm -rf "$build_out"
mkdir -p "$build_out"

echo ">>> Building StaX with cx_Freeze ..."
STAX_BUILD_OUT="$build_out" "$python_bin" setup_freeze.py build_exe

if [ ! -e "$build_out/StaX" ] || [ ! -e "$build_out/StaX_nuke_launcher" ]; then
	echo "cx_Freeze build did not produce expected executables in $build_out" >&2
	exit 1
fi

echo "*** Portable build: $build_out"

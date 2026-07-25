#!/usr/bin/env bash
# Create/reuse a .venv and run StaX directly on Linux.
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(dirname "$script_dir")"
cd "$repo_root"

venv_dir="$repo_root/.venv"
main_py="$repo_root/main.py"
if [ ! -x "$venv_dir/bin/python" ]; then
    echo "[info] creating venv at $venv_dir"
    if command -v uv >/dev/null 2>&1; then
        uv venv --python 3.9 "$venv_dir"
        uv pip install --python "$venv_dir/bin/python" -e .
    else
        python3 -m venv "$venv_dir"
        "$venv_dir/bin/python" -m pip install -e .
    fi
fi

echo "[info] launching StaX"
exec "$venv_dir/bin/python" "$main_py"

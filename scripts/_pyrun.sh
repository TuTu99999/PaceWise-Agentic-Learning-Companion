#!/usr/bin/env bash
# Cross-platform Python launcher for AI log hooks.
# Prefers the repository virtual environment, then tries python3 → python →
# py -3 on PATH. On Windows, it falls back to common Python install locations
# because Git Bash launched by some hooks can get a stripped PATH.
# Designed to be sourced or called as: bash scripts/_pyrun.sh <script> [args...]
#
# Exits 0 silently if no Python is found — hooks must never block the AI tool.
set -u

if [ -x ".venv/Scripts/python.exe" ]; then
  PY=(".venv/Scripts/python.exe")
elif [ -x ".venv/bin/python" ]; then
  PY=(".venv/bin/python")
elif command -v python3 >/dev/null 2>&1 && python3 -c "import sys" >/dev/null 2>&1; then
  PY=(python3)
elif command -v python >/dev/null 2>&1 && python -c "import sys" >/dev/null 2>&1; then
  PY=(python)
elif command -v py >/dev/null 2>&1 && py -3 -c "import sys" >/dev/null 2>&1; then
  PY=(py -3)
else
  # PATH lookup failed — probe standard Windows install locations.
  PY=()
  shopt -s nullglob 2>/dev/null || true
  for cand in \
    /c/Users/*/AppData/Local/Programs/Python/Python*/python.exe \
    "/c/Program Files/Python"*/python.exe \
    "/c/Program Files (x86)/Python"*/python.exe \
    /c/Python*/python.exe; do
    if [ -x "$cand" ] && "$cand" -c "import sys" >/dev/null 2>&1; then
      PY=("$cand")
      break
    fi
  done
  shopt -u nullglob 2>/dev/null || true
  [ ${#PY[@]} -gt 0 ] || exit 0
fi

exec "${PY[@]}" "$@"

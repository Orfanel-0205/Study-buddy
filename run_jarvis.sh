#!/usr/bin/env sh
# Start Jarvis on macOS/Linux. Uses .venv if present, otherwise python3.
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then
  exec .venv/bin/python -m jarvis "$@"
fi
exec python3 -m jarvis "$@"

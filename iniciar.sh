#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$SCRIPT_DIR/app"
LOG_DIR="$APP_DIR/logs"
mkdir -p "$LOG_DIR"

cd "$APP_DIR"

UV="$(command -v uv 2>/dev/null || true)"
if [ -n "$UV" ] && [ -x "$UV" ]; then
    "$UV" run python main.py "$@" 2>>"$LOG_DIR/erro.log"
else
    python3 main.py "$@" 2>>"$LOG_DIR/erro.log"
fi

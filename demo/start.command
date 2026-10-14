#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
exec python3 demo/app.py start --watch-codex --open

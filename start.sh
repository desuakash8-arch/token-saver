#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -e .
.venv/bin/python -m token_saver warmup
printf '\nOpen http://127.0.0.1:8000 in your browser. Press Ctrl+C to stop.\n'
exec .venv/bin/python -m token_saver serve

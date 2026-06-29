#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
python main.py --mode node --env "${1:-env.examples/node.env}" --host "${NODE_HOST_OVERRIDE:-0.0.0.0}" --port "${NODE_API_PORT:-62051}"

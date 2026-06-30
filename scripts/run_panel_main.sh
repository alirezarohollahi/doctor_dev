
#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate
python main.py --mode panel --env "${1:-env.examples/panel.env}" --host "${PANEL_HOST:-0.0.0.0}" --port "${PANEL_PORT:-8080}"




#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
doctor-dev --env ./configs/forigen-node.env

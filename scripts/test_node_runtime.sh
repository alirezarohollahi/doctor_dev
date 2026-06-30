
#!/usr/bin/env bash
set -Eeuo pipefail
BASE_URL="${BASE_URL:-http://127.0.0.1:62051}"
API_KEY="${API_KEY:-11111111-1111-1111-1111-111111111111}"
echo "== health"
curl -fsS "$BASE_URL/health"; echo
echo "== runtime"
curl -fsS -H "Authorization: Bearer $API_KEY" "$BASE_URL/runtime"; echo
echo "== config/export alias"
curl -fsS -H "Authorization: Bearer $API_KEY" "$BASE_URL/config/export"; echo




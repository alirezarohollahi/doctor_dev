
#!/usr/bin/env bash
set -Eeuo pipefail
NODE_A_KEY="lab-node-a-key-11111111-1111-1111-1111-111111111111"
NODE_B_KEY="lab-node-b-key-22222222-2222-2222-2222-222222222222"

echo "Panel health:"
curl -fsS http://127.0.0.1:9000/health; echo

echo "Node A health:"
curl -fsS http://127.0.0.1:9001/health; echo

echo "Node A runtime:"
curl -fsS -H "Authorization: Bearer ${NODE_A_KEY}" http://127.0.0.1:9001/runtime; echo

echo "Node B health:"
curl -fsS http://127.0.0.1:9002/health; echo

echo "Node B runtime:"
curl -fsS -H "Authorization: Bearer ${NODE_B_KEY}" http://127.0.0.1:9002/runtime; echo




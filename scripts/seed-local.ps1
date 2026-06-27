$ErrorActionPreference = "Stop"
$Panel = "http://127.0.0.1:8088"
Invoke-RestMethod -Method Post -Uri "$Panel/api/test-lab/seed-local" | ConvertTo-Json -Depth 10
Invoke-RestMethod -Method Get -Uri "$Panel/api/nodes" | ConvertTo-Json -Depth 10

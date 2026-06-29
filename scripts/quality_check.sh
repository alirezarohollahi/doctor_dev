#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[1/8] Python syntax compile"
python3 -m compileall -q doctor_dev_panel doctor_dev_node main.py tests

echo "[2/8] Static removed-feature scan"
python3 -W ignore::DeprecationWarning -m unittest tests.test_project_quality.StaticQualityTests.test_removed_data_dump_feature_terms_are_absent

echo "[3/8] Runtime/API contract tests"
python3 -W ignore::DeprecationWarning -m unittest tests.test_project_quality.NodeRuntimeContractTests.test_api_identity_reports_actual_bound_port tests.test_project_quality.NodeRuntimeContractTests.test_peer_token_target_and_expiry_checks

echo "[4/8] Atomic apply rollback test"
python3 -W ignore::DeprecationWarning -m unittest tests.test_project_quality.NodeRuntimeContractTests.test_failed_apply_rolls_back_previous_runtime

echo "[5/8] HTTP auth/token integration tests"
python3 -W ignore::DeprecationWarning -m unittest tests.test_node_http_auth

echo "[6/8] Runtime sync concurrency tests"
python3 -W ignore::DeprecationWarning -m unittest tests.test_panel_runtime_sync

echo "[7/8] Panel-to-node end-to-end test"
python3 -W ignore::DeprecationWarning -m unittest tests.test_panel_node_e2e

echo "[8/8] Full quality suite"
python3 -W ignore::DeprecationWarning -m unittest tests.test_project_quality tests.test_node_http_auth tests.test_panel_runtime_sync tests.test_panel_node_e2e

echo "[PASS] Doctor Dev quality checks passed."

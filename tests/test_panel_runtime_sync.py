from __future__ import annotations

import asyncio
import os
import unittest
from unittest.mock import patch


class PanelRuntimeSyncPerformanceTests(unittest.TestCase):
    def test_sync_all_runtime_uses_bounded_concurrency_and_dedupes_nodes(self) -> None:
        async def scenario() -> None:
            from doctor_dev_panel.services import runtime_sync

            old = os.environ.get("DOCTOR_DEV_PANEL_NODE_SYNC_CONCURRENCY")
            os.environ["DOCTOR_DEV_PANEL_NODE_SYNC_CONCURRENCY"] = "2"
            active = 0
            max_active = 0
            call_order: list[str] = []

            async def fake_sync(node: dict) -> dict:
                nonlocal active, max_active
                node_id = str(node.get("id"))
                active += 1
                max_active = max(max_active, active)
                call_order.append(node_id)
                await asyncio.sleep(0.02)
                active -= 1
                return {"ok": True, "node_id": node_id}

            try:
                nodes = [
                    {"id": "node_a"},
                    {"id": "node_b"},
                    {"id": "node_a"},
                    {"id": "node_c"},
                    {"id": "node_d"},
                ]
                with patch("doctor_dev_panel.services.runtime_sync.sync_node_runtime_once", fake_sync):
                    results = await runtime_sync.sync_all_node_runtime(nodes)
                self.assertEqual(["node_a", "node_b", "node_c", "node_d"], [item["node_id"] for item in results])
                self.assertEqual(["node_a", "node_b", "node_c", "node_d"], call_order)
                self.assertLessEqual(max_active, 2)
            finally:
                if old is None:
                    os.environ.pop("DOCTOR_DEV_PANEL_NODE_SYNC_CONCURRENCY", None)
                else:
                    os.environ["DOCTOR_DEV_PANEL_NODE_SYNC_CONCURRENCY"] = old

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main(verbosity=2)

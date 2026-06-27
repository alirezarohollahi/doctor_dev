from __future__ import annotations

import httpx

from doctor_dev_shared.models import ApplyResult, GeneratedConfig, NodeOut


def agent_base_url(node: NodeOut) -> str:
    return f"http://{node.address}:{node.advanced.api_port}"


def auth_headers(node: NodeOut) -> dict[str, str]:
    return {"Authorization": f"Bearer {node.api_key}"}


async def check_agent_status(node: NodeOut) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{agent_base_url(node)}/api/status", headers=auth_headers(node))
        response.raise_for_status()
        return response.json()


async def apply_config(node: NodeOut, config: GeneratedConfig) -> ApplyResult:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{agent_base_url(node)}/api/apply", headers=auth_headers(node), json=config.model_dump())
        response.raise_for_status()
        return ApplyResult.model_validate(response.json())


async def fetch_runtime(node: NodeOut) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{agent_base_url(node)}/api/runtime", headers=auth_headers(node))
        response.raise_for_status()
        return response.json()


async def stop_runtime(node: NodeOut) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(f"{agent_base_url(node)}/api/stop", headers=auth_headers(node))
        response.raise_for_status()
        return response.json()


async def fetch_logs(node: NodeOut, limit: int = 200) -> dict:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(f"{agent_base_url(node)}/api/logs", headers=auth_headers(node), params={"limit": limit})
        response.raise_for_status()
        return response.json()

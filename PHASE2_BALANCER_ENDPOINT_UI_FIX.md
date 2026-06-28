# Phase 2 - Balancer Endpoint UI Fix

This hotfix improves the balancer endpoint editor and prevents invalid endpoint payloads.

## Changes

- Node Inbound endpoint selector now lists inbound names correctly.
- Inbound options include current unsaved core inbounds and saved inbound catalog entries.
- Balancer endpoints are displayed as a two-level tree under each balancer.
- Endpoint cards can be collapsed and expanded.
- The Add Endpoint button is placed after the endpoint list.
- Hidden Node Inbound endpoint port no longer submits an empty string that breaks Pydantic validation.
- Frontend payload normalization converts endpoint port/weight values to safe numeric values.
- Backend schema accepts empty endpoint port values and normalizes them safely.
- Node runtime resolves `node_inbound` endpoints by `core_id`/`inbound_name` before falling back to explicit host/port.
- Panel build config enriches node inbound endpoint references with resolved host/port data for remote node targets.

## Update target

Update both panel and node.

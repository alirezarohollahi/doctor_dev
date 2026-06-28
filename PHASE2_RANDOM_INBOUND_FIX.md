# Phase 2 Random Inbound Runtime Fix

This patch fixes random inbound ports in the core data-plane runtime.

## Fixed

- Random inbound mode now passes runtime validation.
- The node no longer rejects random mode with the old fixed-port-only message.
- Multiple random listeners no longer overwrite each other in the runtime server registry.
- Actual random ports are stored in listener summaries.
- Same-node `Node Inbound` balancer endpoints can resolve random inbounds from the runtime listener table.
- Empty `target_port` values from the UI are normalized before Pydantic validation.
- Node inbound option labels now show `random ×N` instead of looking empty.

## Update scope

Panel and Node should both be updated.

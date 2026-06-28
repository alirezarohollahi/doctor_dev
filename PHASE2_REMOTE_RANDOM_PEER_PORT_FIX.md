# Phase 2 Remote Random Peer Port Fix

Fixes remote random Node Inbound endpoints so UI/random_count placeholders never leak into runtime target ports.

- Remote random peer endpoints now wait for peer runtime sync instead of connecting to placeholder ports.
- Panel enriches endpoint metadata with remote port mode and peer host.
- UI resets semantic Node Inbound endpoint port placeholders when the selected inbound is random.

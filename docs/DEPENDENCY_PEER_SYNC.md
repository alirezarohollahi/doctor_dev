# Dependency-scoped peer runtime sync

When a core on Node B uses a Node Inbound endpoint from Node A, Node B should not treat that endpoint as a static `host:port`.
It should treat it as a semantic dependency:

```text
B Core -> dependency: Node A, sync_interval=N
B Balancer endpoint -> Node A / Core A / Inbound X
```

The panel compiles that dependency into the node-side config with:

- `sync_urls`: Node A runtime/export URLs
- `token_url`: panel endpoint for short-lived peer tokens
- `remote_node_id`
- `remote_core_id`
- `peer_host`
- `sync_interval`
- `token_refresh_interval`

Node B then periodically fetches Node A runtime using a short-lived peer token and updates its local peer runtime cache. This lets Node B keep routing correctly when Node A changes an inbound from fixed ports to random ports, changes the random count, disables an inbound, or changes fixed port lists.

The sync interval lives on the dependency, not on the node record. This lets different cores depend on the same remote node at different cadences.

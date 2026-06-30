import { badge, boolField, emptyState, field, healthDots, jsonBlock, numberField, panel } from "../core/components.js";
import { escapeHtml, nodeById, relativeTime } from "../core/utils.js";

export function defaultNode() {
  return { name: "", address: "127.0.0.1", api_port: 62051, api_key: "", peer_token_refresh_interval: 30, peer_token_ttl: 120, enabled: true };
}

export function renderNodes(state) {
  const selected = nodeById(state, state.selectedNodeId) || state.nodes[0];
  if (selected && !state.selectedNodeId) state.selectedNodeId = selected.id;
  if (state.draftNode) return renderNodeForm(state, state.draftNode, Boolean(state.draftNode.id));
  if (!state.nodes.length) return emptyState("No nodes configured", "Create a node to connect the panel to a runtime agent.", `<button class="btn primary" data-action="new-node">Add Node</button>`, "nodes");
  const list = state.nodes.map((n) => nodeListItem(state, n, selected?.id)).join("");
  return `<div class="master-detail"><aside class="panel-card"><div class="card-title-row"><h2>Nodes</h2><button class="btn primary small" data-action="new-node">Add Node</button></div><div class="master-list">${list}</div></aside><section class="panel-card">${renderNodeDetail(state, selected)}</section></div>`;
}

function nodeListItem(state, node, selectedId) {
  const rt = state.runtimeCache?.nodes?.[node.id] || {};
  return `<button class="list-item ${String(node.id) === String(selectedId) ? "active" : ""}" data-select-node="${escapeHtml(node.id)}"><div class="item-title"><span>${escapeHtml(node.name)}</span>${badge(node.enabled ? node.status || "pending" : "disabled")}</div><div class="item-meta"><span class="mono">${escapeHtml(node.address)}:${escapeHtml(node.api_port)}</span>${healthDots({ reachable: rt.reachable, auth: rt.auth_ok, runtime: rt.runtime_ok })}</div></button>`;
}

function renderNodeDetail(state, node) {
  if (!node) return "";
  const rt = state.runtimeCache?.nodes?.[node.id] || {};
  const tab = state.selectedNodeTab || "overview";
  const tabs = ["overview", "runtime", "drift", "preview", "metadata"].map((id) => `<button class="tab ${tab === id ? "active" : ""}" data-node-tab="${id}">${label(id)}</button>`).join("");
  const actions = `<button class="btn small" data-action="check-node" data-node-id="${escapeHtml(node.id)}">Check</button><button class="btn small" data-action="sync-node" data-node-id="${escapeHtml(node.id)}">Sync Runtime</button><button class="btn small primary" data-action="apply-node" data-node-id="${escapeHtml(node.id)}">Apply Config</button><button class="btn small" data-action="edit-node" data-node-id="${escapeHtml(node.id)}">Edit</button><button class="btn small danger" data-action="delete-node" data-node-id="${escapeHtml(node.id)}">Delete</button>`;
  return `<div class="card-title-row"><div><h2>${escapeHtml(node.name)}</h2><div class="muted mono">${escapeHtml(node.id)}</div></div><div class="toolbar">${actions}</div></div><div class="tabs">${tabs}</div>${tabContent(state, node, rt, tab)}`;
}

function tabContent(state, node, rt, tab) {
  if (tab === "runtime") return renderRuntimeTab(rt);
  if (tab === "drift") return `<div data-node-drift-panel="${escapeHtml(node.id)}">${jsonBlock(state.nodeDrift || { hint: "Click View Drift or refresh runtime to load drift details." })}</div><div class="toolbar"><button class="btn" data-action="load-drift" data-node-id="${escapeHtml(node.id)}">Refresh Drift</button></div>`;
  if (tab === "preview") return `<div data-node-preview-panel="${escapeHtml(node.id)}">${jsonBlock(state.nodePreview || { hint: "Click Load Config Preview." })}</div><div class="toolbar"><button class="btn" data-action="load-preview" data-node-id="${escapeHtml(node.id)}">Load Config Preview</button><button class="btn primary" data-action="apply-node" data-node-id="${escapeHtml(node.id)}">Apply</button></div>`;
  if (tab === "metadata") return jsonBlock(node);
  return `<div class="grid cols-2"><dl class="kv"><dt>Name</dt><dd>${escapeHtml(node.name)}</dd><dt>Address</dt><dd class="mono">${escapeHtml(node.address)}:${escapeHtml(node.api_port)}</dd><dt>Status</dt><dd>${badge(node.enabled ? node.status || "pending" : "disabled")}</dd><dt>Peer Refresh</dt><dd>${escapeHtml(node.peer_token_refresh_interval)}s</dd><dt>Peer TTL</dt><dd>${escapeHtml(node.peer_token_ttl)}s</dd><dt>Last Checked</dt><dd>${escapeHtml(relativeTime(node.last_checked_at))}</dd></dl><dl class="kv"><dt>Reachable</dt><dd>${badge(String(Boolean(rt.reachable)), rt.reachable ? "good" : "warn")}</dd><dt>Auth</dt><dd>${badge(String(Boolean(rt.auth_ok)), rt.auth_ok ? "good" : "warn")}</dd><dt>Runtime</dt><dd>${badge(String(Boolean(rt.runtime_ok)), rt.runtime_ok ? "good" : "warn")}</dd><dt>Listeners</dt><dd>${escapeHtml(rt.listeners?.length ?? rt.summary?.listeners_total ?? 0)}</dd><dt>Error</dt><dd>${escapeHtml(rt.last_error || node.last_error || "—")}</dd></dl></div>`;
}

function renderRuntimeTab(rt) {
  if (!rt || !Object.keys(rt).length) return `<div class="empty-state"><h3>No runtime cache</h3><p>Sync this node to load runtime state.</p></div>`;
  const listeners = rt.listeners || rt.summary?.listeners || [];
  const advertised = rt.summary?.advertised_inbounds || [];
  return `<div class="grid"><div class="grid cols-3"><article class="mini-card"><strong>Reachable</strong>${badge(String(Boolean(rt.reachable)), rt.reachable ? "good" : "bad")}</article><article class="mini-card"><strong>Auth</strong>${badge(String(Boolean(rt.auth_ok)), rt.auth_ok ? "good" : "bad")}</article><article class="mini-card"><strong>Runtime</strong>${badge(String(Boolean(rt.runtime_ok)), rt.runtime_ok ? "good" : "bad")}</article></div>${panel("Listeners", listenerTable(listeners))}${panel("Advertised Inbounds", advertisedTable(advertised))}${panel("Peer Sync", jsonBlock(rt.summary?.peer_sync_errors || {}))}</div>`;
}

function listenerTable(items) {
  if (!items.length) return `<p class="muted">No listeners reported.</p>`;
  return `<div class="table-wrap"><table><thead><tr><th>Core</th><th>Inbound</th><th>Bind</th><th>Requested</th><th>Actual</th><th>Status</th></tr></thead><tbody>${items.map((x) => `<tr><td>${escapeHtml(x.core_name || x.core_id)}</td><td>${escapeHtml(x.inbound_name)}</td><td class="mono">${escapeHtml(x.bind_ip)}</td><td class="mono">${escapeHtml(x.requested_port)}</td><td class="mono">${escapeHtml(x.port)}</td><td>${badge(x.status)}</td></tr>`).join("")}</tbody></table></div>`;
}

function advertisedTable(items) {
  if (!items.length) return `<p class="muted">No advertised inbounds reported.</p>`;
  return `<div class="table-wrap"><table><thead><tr><th>Core</th><th>Inbound</th><th>Public Host</th><th>Mode</th><th>Ports</th><th>Status</th></tr></thead><tbody>${items.map((x) => `<tr><td>${escapeHtml(x.core_name || x.core_id)}</td><td>${escapeHtml(x.inbound_name)}</td><td class="mono">${escapeHtml(x.public_host || "fallback")}</td><td>${badge(x.public_ports_mode || "use_inbound_ports")}</td><td class="mono">${escapeHtml((x.public_ports || []).join(", "))}</td><td>${badge(x.status || "advertised")}</td></tr>`).join("")}</tbody></table></div>`;
}

function renderNodeForm(state, node, editing) {
  return `<section class="panel-card"><div class="card-title-row"><h2>${editing ? "Edit Node" : "Add Node"}</h2><button class="btn ghost" data-action="cancel-node-edit">Cancel</button></div><form id="nodeForm" class="form-grid"><div class="form-grid two">${field("Node Name", "name", node.name, "required maxlength=120", "Human-readable node label")}${field("Node Address", "address", node.address, "required maxlength=255", "Panel control address or domain")}${numberField("API Port", "api_port", node.api_port, "required min=1 max=65535")}${field("API Key", "api_key", node.api_key, "required maxlength=255", "Node management API key")}${numberField("Peer Token Refresh Interval", "peer_token_refresh_interval", node.peer_token_refresh_interval, "required min=5 max=86400", "Seconds")}${numberField("Peer Token TTL", "peer_token_ttl", node.peer_token_ttl, "required min=10 max=86400", "Seconds")}${boolField("Enabled", "enabled", node.enabled)}</div><div class="toolbar"><button class="btn" type="button" data-action="generate-node-key">Generate API Key</button><button class="btn" type="button" data-action="check-draft-node">Check Draft</button><button class="btn primary" type="submit">${editing ? "Save Node" : "Create Node"}</button></div></form></section>`;
}

function label(id) { return ({ overview: "Overview", runtime: "Runtime", drift: "Drift", preview: "Config Preview", metadata: "Metadata" })[id] || id; }

import { badge, boolField, emptyState, field, jsonBlock, numberField, panel, selectField, textArea } from "../core/components.js";
import { catalogForNode, clone, coreById, escapeHtml, firstCoreForNode, nodeById, nodeName, parsePorts, portsText } from "../core/utils.js";

export function defaultInbound() {
  return { name: "inbound-1", bind_ip: "0.0.0.0", public_host: "", public_ports_mode: "use_inbound_ports", public_fixed_ports: [], public_random_count: 1, port_mode: "fixed", fixed_ports: [], random_count: 1, target_type: "static", target_host: "127.0.0.1", target_port: 80, target_balancer: "", enabled: true, notes: "" };
}
export function defaultBalancer() { return { alias: "balancer-1", strategy: "round_robin", endpoints: [], enabled: true, notes: "" }; }
export function defaultEndpoint() { return { type: "static", host: "127.0.0.1", port: 80, dependency_id: "", node_id: "", core_id: "", inbound_name: "", weight: 1, enabled: true, notes: "" }; }
export function defaultDependency(index = 0) { return { id: `dep_${Math.random().toString(16).slice(2, 10)}`, type: "node", name: `dep ${index + 1}`, ref_id: "", host: "", sync_interval: 5, required: true, notes: "" }; }
export function defaultCore(state) { return { name: "New Core", node_id: state.nodes[0]?.id || "", enabled: true, inbounds: [], balancers: [], dependencies: [], advanced_config: { enabled: false, json_config: "" } }; }

export function renderCores(state) {
  if (state.draftCore) return renderCoreWorkspace(state);
  const selected = coreById(state, state.selectedCoreId) || state.cores[0];
  if (selected && !state.selectedCoreId) state.selectedCoreId = selected.id;
  if (!state.cores.length) return emptyState("No cores configured", "Create a core to define inbounds, dependencies and balancers for a node.", `<button class="btn primary" data-action="new-core">Add Core</button>`, "cores");
  const list = state.cores.map((c) => coreListItem(state, c, selected?.id)).join("");
  return `<div class="master-detail"><aside class="panel-card"><div class="card-title-row"><h2>Cores</h2><button class="btn primary small" data-action="new-core">Add Core</button></div><div class="master-list">${list}</div></aside><section class="panel-card">${renderCoreDetail(state, selected)}</section></div>`;
}

function coreListItem(state, core, selectedId) {
  return `<button class="list-item ${String(core.id) === String(selectedId) ? "active" : ""}" data-select-core="${escapeHtml(core.id)}"><div class="item-title"><span>${escapeHtml(core.name)}</span>${badge(core.enabled ? core.status || "ready" : "disabled")}</div><div class="item-meta"><span>${escapeHtml(nodeName(state, core.node_id))}</span><span>${(core.inbounds||[]).length} in</span><span>${(core.balancers||[]).length} bal</span><span>${(core.dependencies||[]).length} dep</span></div></button>`;
}

function renderCoreDetail(state, core) {
  if (!core) return "";
  return `<div class="card-title-row"><div><h2>${escapeHtml(core.name)}</h2><div class="muted">${escapeHtml(nodeName(state, core.node_id))} · ${escapeHtml(core.id)}</div></div><div class="toolbar"><button class="btn small" data-action="preview-core" data-core-id="${escapeHtml(core.id)}">Preview</button><button class="btn small primary" data-action="apply-core" data-core-id="${escapeHtml(core.id)}">Apply</button><button class="btn small" data-action="edit-core" data-core-id="${escapeHtml(core.id)}">Edit</button><button class="btn small danger" data-action="delete-core" data-core-id="${escapeHtml(core.id)}">Delete</button></div></div><div class="grid cols-3"><article class="mini-card"><strong>Inbounds</strong><span>${(core.inbounds || []).length}</span></article><article class="mini-card"><strong>Balancers</strong><span>${(core.balancers || []).length}</span></article><article class="mini-card"><strong>Dependencies</strong><span>${(core.dependencies || []).length}</span></article></div>${panel("Routing Summary", routingSummary(state, core))}`;
}

function routingSummary(state, core) {
  const ins = (core.inbounds || []).map((ib) => `<div class="mini-card"><div class="item-title"><strong>${escapeHtml(ib.name)}</strong>${badge(ib.enabled ? "enabled" : "disabled", ib.enabled ? "good" : "disabled")}</div><div class="route-preview"><div class="preview-row"><span>Listen</span><code class="mono">${escapeHtml(ib.bind_ip || "0.0.0.0")}:${escapeHtml(ib.port_mode === "random" ? `random × ${ib.random_count}` : (ib.fixed_ports || []).join(","))}</code></div><div class="preview-row"><span>Advertise</span><code class="mono">${escapeHtml(ib.public_host || "node address fallback")}:${escapeHtml(publicPortsSummary(ib))}</code></div><div class="preview-row"><span>Target</span><code class="mono">${escapeHtml(targetSummary(ib))}</code></div></div></div>`).join("");
  return ins || `<p class="muted">No inbounds yet.</p>`;
}

export function renderCoreWorkspace(state) {
  const core = state.draftCore;
  const tab = state.selectedCoreTab || "overview";
  const tabs = ["overview", "inbounds", "balancers", "dependencies", "advanced", "preview"].map((id) => `<button class="tab ${tab === id ? "active" : ""}" data-core-tab="${id}">${tabLabel(id)}</button>`).join("");
  return `<section class="panel-card"><div class="card-title-row"><div><h2>${escapeHtml(core.id ? `Edit ${core.name}` : "Create Core")}</h2><div class="muted">${state.dirtyCore ? "Unsaved changes" : "Draft ready"}</div></div><div class="toolbar"><button class="btn ghost" data-action="cancel-core-edit">Cancel</button><button class="btn" data-action="save-core">Save</button><button class="btn primary" data-action="save-apply-core">Save & Apply</button></div></div>${state.dirtyCore ? `<div class="notice">You have unsaved routing changes. Save before applying to runtime.</div>` : ""}<div class="tabs">${tabs}</div>${renderCoreTab(state, core, tab)}</section>`;
}

function renderCoreTab(state, core, tab) {
  if (tab === "inbounds") return renderInbounds(state, core);
  if (tab === "balancers") return renderBalancers(state, core);
  if (tab === "dependencies") return renderDependencies(state, core);
  if (tab === "advanced") return renderAdvanced(core);
  if (tab === "preview") return renderPreview(state, core);
  return renderOverview(state, core);
}

function renderOverview(state, core) {
  return `<div class="form-grid"><div class="form-grid three">${field("Core Name", "name", core.name, "data-core-field=\"name\" required maxlength=120")}${selectField("Node", "node_id", [{ value: "", label: "Select node" }, ...state.nodes.map((n) => ({ value: n.id, label: `${n.name} (${n.address}:${n.api_port})` }))], core.node_id)}${boolField("Enabled", "enabled", core.enabled)}</div><div class="grid cols-3"><article class="mini-card"><strong>Inbounds</strong>${(core.inbounds||[]).length}</article><article class="mini-card"><strong>Balancers</strong>${(core.balancers||[]).length}</article><article class="mini-card"><strong>Dependencies</strong>${(core.dependencies||[]).length}</article></div></div>`;
}

function renderInbounds(state, core) {
  const items = (core.inbounds || []).map((ib, i) => renderInboundEditor(state, core, ib, i)).join("");
  return `<div class="toolbar between"><h3>Inbounds</h3><div class="toolbar"><button class="btn small" data-action="set-core-collapse" data-scope="inbounds" data-mode="close">Close all</button><button class="btn small" data-action="set-core-collapse" data-scope="inbounds" data-mode="open">Open all</button><button class="btn primary small" data-action="add-inbound">Add Inbound</button></div></div><div class="grid">${items || emptyState("No inbounds", "Inbounds define local listeners and public advertised routes.", `<button class="btn primary" data-action="add-inbound">Add Inbound</button>`, "runtime")}</div>`;
}

function renderInboundEditor(state, core, ib, i) {
  const key = collapseKey(core, `inbound:${i}`);
  const collapsed = isCollapsed(state, key);
  const balancerOptions = [{ value: "", label: "Select balancer" }, ...(core.balancers || []).map((b) => ({ value: b.alias, label: b.alias }))];
  const body = collapsed ? inboundCompact(ib) : `<div class="collapsible-body"><div class="split"><section class="mini-card nested-card"><h3>Local Listen</h3><div class="form-grid two">${field("Name", `inbounds.${i}.name`, ib.name, `data-inbound-field="name" data-index="${i}" required`)}${field("Bind IP", `inbounds.${i}.bind_ip`, ib.bind_ip || "0.0.0.0", `data-inbound-field="bind_ip" data-index="${i}"`)}${selectField("Listen Port Mode", `inbounds.${i}.port_mode`, ["fixed", "random"], ib.port_mode)}${ib.port_mode === "random" ? numberField("Random Count", `inbounds.${i}.random_count`, ib.random_count, `data-inbound-field="random_count" data-index="${i}" min=1 max=4096`) : field("Fixed Listen Ports", `inbounds.${i}.fixed_ports`, portsText(ib.fixed_ports), `data-inbound-field="fixed_ports" data-index="${i}" placeholder="8787,8788"`)}</div></section><section class="mini-card nested-card"><h3>Public Advertisement</h3><div class="form-grid two">${field("Public Host", `inbounds.${i}.public_host`, ib.public_host || "", `data-inbound-field="public_host" data-index="${i}" placeholder="node-a.example.com"`, "Empty means node address/server IP fallback")}${selectField("Public Ports Mode", `inbounds.${i}.public_ports_mode`, [{value:"use_inbound_ports", label:"use inbound ports"}, "random", "fixed"], ib.public_ports_mode || "use_inbound_ports")}${ib.public_ports_mode === "random" ? numberField("Public Random Count", `inbounds.${i}.public_random_count`, ib.public_random_count, `data-inbound-field="public_random_count" data-index="${i}" min=1 max=4096`) : ""}${ib.public_ports_mode === "fixed" ? field("Public Fixed Ports", `inbounds.${i}.public_fixed_ports`, portsText(ib.public_fixed_ports), `data-inbound-field="public_fixed_ports" data-index="${i}" placeholder="443,8443"`) : ""}</div></section></div><div class="route-preview"><div class="preview-row"><span>Listen</span><code class="mono">${escapeHtml(ib.bind_ip || "0.0.0.0")}:${escapeHtml(ib.port_mode === "random" ? `random × ${ib.random_count || 1}` : portsText(ib.fixed_ports) || "no ports")}</code></div><div class="preview-row"><span>Advertise</span><code class="mono">${escapeHtml(ib.public_host || "node address fallback")}:${escapeHtml(publicPortsSummary(ib))}</code></div><div class="preview-row"><span>Target</span><code class="mono">${escapeHtml(targetSummary(ib))}</code></div></div><section class="mini-card nested-card"><h3>Target</h3><div class="form-grid three">${selectField("Target Type", `inbounds.${i}.target_type`, ["static", "balancer"], ib.target_type)}${ib.target_type === "balancer" ? selectField("Target Balancer", `inbounds.${i}.target_balancer`, balancerOptions, ib.target_balancer) : `${field("Target Host", `inbounds.${i}.target_host`, ib.target_host || "127.0.0.1", `data-inbound-field="target_host" data-index="${i}"`)}${numberField("Target Port", `inbounds.${i}.target_port`, ib.target_port || 80, `data-inbound-field="target_port" data-index="${i}" min=1 max=65535`)}`}${boolField("Enabled", `inbounds.${i}.enabled`, ib.enabled)}${textArea("Notes", `inbounds.${i}.notes`, ib.notes || "", `data-inbound-field="notes" data-index="${i}"`)}</div></section></div>`;
  return `<article class="mini-card collapsible-card ${collapsed ? "is-collapsed" : ""}" data-inbound-index="${i}"><div class="card-title-row collapsible-head"><div><h3>${escapeHtml(ib.name || `Inbound ${i + 1}`)}</h3><div class="item-meta"><span>${escapeHtml(ib.port_mode === "random" ? `random × ${ib.random_count || 1}` : portsText(ib.fixed_ports) || "no ports")}</span><span>${escapeHtml(targetSummary(ib))}</span></div></div><div class="row-actions">${collapseButton(key, collapsed)}<button class="btn small danger" data-action="remove-inbound" data-index="${i}">Remove</button></div></div>${body}</article>`;
}

function renderDependencies(state, core) {
  const items = (core.dependencies || []).map((dep, i) => renderDependency(state, core, dep, i)).join("");
  return `<div class="toolbar between"><h3>Node Dependencies</h3><div class="toolbar"><button class="btn small" data-action="set-core-collapse" data-scope="dependencies" data-mode="close">Close all</button><button class="btn small" data-action="set-core-collapse" data-scope="dependencies" data-mode="open">Open all</button><button class="btn primary small" data-action="add-dependency">Add Dependency</button></div></div><div class="grid">${items || emptyState("No dependencies", "Add a remote node dependency before using Node Inbound balancer endpoints.", `<button class="btn primary" data-action="add-dependency">Add Dependency</button>`, "nodes")}</div>`;
}

function renderDependency(state, core, dep, i) {
  const key = collapseKey(core, `dependency:${i}`);
  const collapsed = isCollapsed(state, key);
  const used = dependencyUseCount(core, dep.id);
  const nodeOptions = [{ value: "", label: "Select remote node" }, ...state.nodes.filter((n) => String(n.id) !== String(core.node_id)).map((n) => ({ value: n.id, label: `${n.name} (${n.address})` }))];
  const body = collapsed ? `<div class="route-preview compact-preview"><div class="preview-row"><span>Remote</span><code class="mono">${escapeHtml(nodeName(state, dep.ref_id) || "missing node")}</code></div><div class="preview-row"><span>Sync</span><code class="mono">${escapeHtml(dep.sync_interval || 5)}s · ${escapeHtml(dep.required === false ? "optional" : "required")}</code></div></div>` : `<div class="collapsible-body"><div class="form-grid three">${field("Dependency Name", `dependencies.${i}.name`, dep.name || `dep ${i + 1}`, `data-dep-field="name" data-index="${i}" maxlength=120`)}${selectField("Remote Node", `dependencies.${i}.ref_id`, nodeOptions, dep.ref_id)}${field("Host Override", `dependencies.${i}.host`, dep.host || "", `data-dep-field="host" data-index="${i}" placeholder="a1.example.com"`, "Empty uses advertised public host or node address fallback")}${numberField("Sync Interval", `dependencies.${i}.sync_interval`, dep.sync_interval || 5, `data-dep-field="sync_interval" data-index="${i}" min=1 max=86400`, "Seconds")}${boolField("Required", `dependencies.${i}.required`, dep.required)}${textArea("Notes", `dependencies.${i}.notes`, dep.notes || "", `data-dep-field="notes" data-index="${i}"`)}</div></div>`;
  return `<article class="mini-card collapsible-card ${collapsed ? "is-collapsed" : ""}" data-dependency-index="${i}"><div class="card-title-row collapsible-head"><div><h3>${escapeHtml(dep.name || `dep ${i + 1}`)}</h3><div class="item-meta"><span>${escapeHtml(nodeName(state, dep.ref_id) || "no node")}</span><span>${escapeHtml(dep.host || "default host")}</span></div></div><div class="row-actions">${used ? badge(`${used} endpoint${used > 1 ? "s" : ""}`, "warn") : ""}${collapseButton(key, collapsed)}<button class="btn small danger" data-action="remove-dependency" data-index="${i}" ${used ? "data-used=1" : ""}>Remove</button></div></div>${body}</article>`;
}

function renderBalancers(state, core) {
  const items = (core.balancers || []).map((b, i) => renderBalancer(state, core, b, i)).join("");
  return `<div class="toolbar between"><h3>Balancers</h3><div class="toolbar"><button class="btn small" data-action="set-core-collapse" data-scope="balancers" data-mode="close">Close all balancers</button><button class="btn small" data-action="set-core-collapse" data-scope="balancers" data-mode="open">Open all balancers</button><button class="btn primary small" data-action="add-balancer">Add Balancer</button></div></div><div class="grid">${items || emptyState("No balancers", "Balancers group static and node-inbound targets with routing strategy.", `<button class="btn primary" data-action="add-balancer">Add Balancer</button>`, "cores")}</div>`;
}

function renderBalancer(state, core, b, bi) {
  const key = collapseKey(core, `balancer:${bi}`);
  const collapsed = isCollapsed(state, key);
  const eps = (b.endpoints || []).map((ep, ei) => renderEndpoint(state, core, ep, bi, ei)).join("");
  const endpointCount = (b.endpoints || []).length;
  const body = collapsed ? balancerCompact(b, endpointCount) : `<div class="collapsible-body"><div class="form-grid three">${field("Alias", `balancers.${bi}.alias`, b.alias, `data-balancer-field="alias" data-index="${bi}" required`)}${selectField("Strategy", `balancers.${bi}.strategy`, ["round_robin", "random", "failover", "least_connections"], b.strategy)}${boolField("Enabled", `balancers.${bi}.enabled`, b.enabled)}${textArea("Notes", `balancers.${bi}.notes`, b.notes || "", `data-balancer-field="notes" data-index="${bi}"`)}</div><div class="toolbar between endpoint-toolbar"><h3 class="section-title">Endpoints</h3><button class="btn small" data-action="add-endpoint" data-index="${bi}">Add Endpoint</button></div><div class="grid">${eps || `<div class="notice">No endpoints yet. Add a static target or a dependency-backed Node Inbound endpoint.</div>`}</div></div>`;
  return `<article class="mini-card collapsible-card ${collapsed ? "is-collapsed" : ""}" data-balancer-index="${bi}"><div class="card-title-row collapsible-head"><div><h3>${escapeHtml(b.alias || `balancer ${bi + 1}`)}</h3><div class="item-meta"><span>${escapeHtml(b.strategy || "round_robin")}</span><span>${endpointCount} endpoint${endpointCount === 1 ? "" : "s"}</span></div></div><div class="row-actions">${badge(b.enabled ? "enabled" : "disabled", b.enabled ? "good" : "disabled")}${collapseButton(key, collapsed)}<button class="btn small" data-action="add-endpoint" data-index="${bi}">Add Endpoint</button><button class="btn small danger" data-action="remove-balancer" data-index="${bi}">Remove</button></div></div>${body}</article>`;
}

function renderEndpoint(state, core, ep, bi, ei) {
  const key = collapseKey(core, `balancer:${bi}:endpoint:${ei}`);
  const collapsed = isCollapsed(state, key);
  const deps = core.dependencies || [];
  const dep = deps.find((d) => String(d.id) === String(ep.dependency_id));
  const depNodeId = dep?.ref_id || ep.node_id;
  const catalog = catalogForNode(state, depNodeId);
  const coreOptions = [{ value: "", label: "Select remote core" }, ...uniqueCatalogCores(catalog)];
  const inboundOptions = [{ value: "", label: "Select remote inbound" }, ...catalog.filter((x) => !ep.core_id || String(x.core_id) === String(ep.core_id)).map((x) => ({ value: x.inbound_name || x.name, label: inboundOptionLabel(x) }))];
  const depOptions = [{ value: "", label: deps.length ? "Select dependency" : "Add a dependency first" }, ...deps.map((d) => ({ value: d.id, label: `${d.name || d.id} → ${nodeName(state, d.ref_id)}${d.host ? ` via ${d.host}` : ""}` }))];
  const body = collapsed ? `<div class="route-preview compact-preview"><div class="preview-row"><span>Resolved</span><code class="mono">${escapeHtml(endpointSummary(state, core, ep))}</code></div></div>` : `<div class="collapsible-body"><div class="form-grid three">${selectField("Endpoint Type", `balancers.${bi}.endpoints.${ei}.type`, ["static", "node_inbound"], ep.type)}${ep.type === "node_inbound" ? `${deps.length ? "" : `<div class="notice bad">Add a node dependency before using Node Inbound endpoints.</div>`}${selectField("Dependency", `balancers.${bi}.endpoints.${ei}.dependency_id`, depOptions, ep.dependency_id)}${selectField("Remote Core", `balancers.${bi}.endpoints.${ei}.core_id`, coreOptions, ep.core_id)}${selectField("Remote Inbound", `balancers.${bi}.endpoints.${ei}.inbound_name`, inboundOptions, ep.inbound_name)}` : `${field("Host", `balancers.${bi}.endpoints.${ei}.host`, ep.host || "127.0.0.1", `data-endpoint-field="host" data-balancer="${bi}" data-index="${ei}"`)}${numberField("Port", `balancers.${bi}.endpoints.${ei}.port`, ep.port || 80, `data-endpoint-field="port" data-balancer="${bi}" data-index="${ei}" min=1 max=65535`)}`}${numberField("Weight", `balancers.${bi}.endpoints.${ei}.weight`, ep.weight ?? 1, `data-endpoint-field="weight" data-balancer="${bi}" data-index="${ei}" min=0 step=0.1`)}${boolField("Enabled", `balancers.${bi}.endpoints.${ei}.enabled`, ep.enabled)}${textArea("Notes", `balancers.${bi}.endpoints.${ei}.notes`, ep.notes || "", `data-endpoint-field="notes" data-balancer="${bi}" data-index="${ei}"`)}</div><div class="route-preview"><div class="preview-row"><span>Resolved</span><code class="mono">${escapeHtml(endpointSummary(state, core, ep))}</code></div></div></div>`;
  return `<article class="endpoint-row collapsible-card ${collapsed ? "is-collapsed" : ""}" data-endpoint-index="${bi}.${ei}"><div class="card-title-row collapsible-head"><div><strong>${escapeHtml(ep.type === "node_inbound" ? "Node Inbound" : "Static Endpoint")}</strong><div class="item-meta"><span>${escapeHtml(endpointSummary(state, core, ep))}</span></div></div><div class="row-actions">${badge(ep.enabled ? "enabled" : "disabled", ep.enabled ? "good" : "disabled")}${collapseButton(key, collapsed)}<button class="btn small danger" data-action="remove-endpoint" data-balancer="${bi}" data-index="${ei}">Remove</button></div></div>${body}</article>`;
}

function collapseKey(core, suffix) {
  return `core:${core.id || "draft"}:${suffix}`;
}

function isCollapsed(state, key) {
  return Boolean((state.uiCollapsed || {})[key]);
}

function collapseButton(key, collapsed) {
  return `<button type="button" class="btn small ghost collapse-toggle" data-action="toggle-ui-collapse" data-collapse-key="${escapeHtml(key)}" aria-expanded="${collapsed ? "false" : "true"}">${collapsed ? "Open" : "Close"}</button>`;
}

function inboundCompact(ib) {
  return `<div class="route-preview compact-preview"><div class="preview-row"><span>Listen</span><code class="mono">${escapeHtml(ib.bind_ip || "0.0.0.0")}:${escapeHtml(ib.port_mode === "random" ? `random × ${ib.random_count || 1}` : portsText(ib.fixed_ports) || "no ports")}</code></div><div class="preview-row"><span>Advertise</span><code class="mono">${escapeHtml(ib.public_host || "node address fallback")}:${escapeHtml(publicPortsSummary(ib))}</code></div><div class="preview-row"><span>Target</span><code class="mono">${escapeHtml(targetSummary(ib))}</code></div></div>`;
}

function balancerCompact(b, endpointCount) {
  return `<div class="route-preview compact-preview"><div class="preview-row"><span>Strategy</span><code class="mono">${escapeHtml(b.strategy || "round_robin")}</code></div><div class="preview-row"><span>Endpoints</span><code class="mono">${endpointCount} endpoint${endpointCount === 1 ? "" : "s"}</code></div><div class="preview-row"><span>Status</span><code class="mono">${escapeHtml(b.enabled ? "enabled" : "disabled")}</code></div></div>`;
}

function renderAdvanced(core) {
  const adv = core.advanced_config || { enabled: false, json_config: "" };
  return `<div class="form-grid">${boolField("Enable Advanced JSON", "advanced_config.enabled", adv.enabled)}${textArea("JSON Config", "advanced_config.json_config", adv.json_config || "", "rows=18", "Validate before saving or applying.")}<div class="toolbar"><button class="btn" data-action="validate-advanced">Validate JSON</button></div><div id="advancedValidation"></div></div>`;
}

function renderPreview(state, core) {
  return `<div class="grid"><div class="toolbar"><button class="btn" data-action="preview-draft-core">Build Preview</button><button class="btn primary" data-action="save-apply-core">Save & Apply</button></div>${jsonBlock(state.corePreview || core)}</div>`;
}

function publicPortsSummary(ib) {
  const mode = ib.public_ports_mode || "use_inbound_ports";
  if (mode === "fixed") return portsText(ib.public_fixed_ports) || "no public ports";
  if (mode === "random") return `public random × ${ib.public_random_count || 1}`;
  return ib.port_mode === "random" ? `listen random × ${ib.random_count || 1}` : portsText(ib.fixed_ports) || "listen ports";
}

function targetSummary(ib) {
  if (ib.target_type === "balancer") return `balancer:${ib.target_balancer || "missing"}`;
  return `${ib.target_host || "127.0.0.1"}:${ib.target_port || 80}`;
}

function endpointSummary(state, core, ep) {
  if (ep.type === "node_inbound") {
    const dep = (core.dependencies || []).find((d) => String(d.id) === String(ep.dependency_id));
    return dep ? `${dep.name || dep.id} / ${nodeName(state, dep.ref_id)} / ${ep.core_id || "remote core"} / ${ep.inbound_name || "remote inbound"}` : "missing dependency";
  }
  return `${ep.host || "127.0.0.1"}:${ep.port || 80}`;
}

function dependencyUseCount(core, depId) {
  let count = 0;
  for (const b of core.balancers || []) for (const ep of b.endpoints || []) if (String(ep.dependency_id || "") === String(depId || "")) count++;
  return count;
}

function uniqueCatalogCores(catalog) {
  const seen = new Set();
  const options = [];
  for (const item of catalog || []) {
    const id = item.core_id || "";
    if (!id || seen.has(id)) continue;
    seen.add(id);
    options.push({ value: id, label: item.core_name || id });
  }
  return options;
}

export function inboundOptionLabel(item) {
  const core = item.core_name ? `${item.core_name} / ` : "";
  return `${core}${item.inbound_name || item.name || "inbound"}`;
}

function tabLabel(id) { return ({ overview: "Overview", inbounds: "Inbounds", balancers: "Balancers", dependencies: "Dependencies", advanced: "Advanced JSON", preview: "Preview / Apply" })[id] || id; }




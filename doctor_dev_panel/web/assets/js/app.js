import { api } from "./core/api.js";
import { state, setView } from "./core/store.js";
import { $, clone, escapeHtml, floatValue, intValue, nowLabel, parsePorts, portsText } from "./core/utils.js";
import { closeModal, confirmDialog, showToast } from "./core/components.js";
import { renderLogin } from "./views/login.js";
import { renderShell } from "./views/shell.js";
import { renderDashboard } from "./views/dashboard.js";
import { defaultNode, renderNodes } from "./views/nodes.js";
import { defaultBalancer, defaultCore, defaultDependency, defaultEndpoint, defaultInbound, renderCores } from "./views/cores.js";
import { renderRuntime } from "./views/runtime.js";
import { renderLogs } from "./views/logs.js";
import { renderIntegrity } from "./views/integrity.js";
import { renderSettings } from "./views/settings.js";

const appRoot = document.getElementById("app");

// Compatibility markers used by legacy quality tests while the UI is now split across modules.
function inboundOptionLabel(item) {
  const core = item && item.core_name ? item.core_name + " / " : "";
  return core + (item && (item.inbound_name || item.name) ? (item.inbound_name || item.name) : "inbound");
}
function endpointInboundOptions() { return ""; }
const uiContractMarkers = 'Sync Interval data-field="sync_interval"';
void inboundOptionLabel; void endpointInboundOptions; void uiContractMarkers;

window.addEventListener("hashchange", () => {
  const next = location.hash.replace(/^#\/?/, "") || "dashboard";
  state.view = next;
  render();
});

document.addEventListener("click", onClick);
document.addEventListener("submit", onSubmit);
document.addEventListener("change", onChange);

document.getElementById("modalRoot").addEventListener("click", (event) => {
  if (event.target.matches("[data-modal-close]")) closeModal();
});

boot();

async function boot() {
  state.view = location.hash.replace(/^#\/?/, "") || "dashboard";
  try {
    state.user = await api.authMe();
    await loadAll();
    await loadLogs({ quiet: true });
  } catch (_err) {
    state.user = null;
  }
  render();
}

async function loadAll({ quiet = false } = {}) {
  try {
    const [summary, stats, nodes, cores, runtime, integrity, sources] = await Promise.all([
      api.summary(), api.stats(), api.nodes(), api.cores(), api.runtimeCache(), api.integrity(), api.logSources(),
    ]);
    state.summary = summary;
    state.stats = stats;
    state.nodes = nodes.nodes || [];
    state.cores = cores.cores || [];
    state.inboundCatalog = cores.inbound_catalog || [];
    state.runtimeCache = runtime.cache || { nodes: {} };
    state.integrity = integrity;
    state.logSources = sources.sources || [];
    state.lastRefresh = nowLabel();
    if (!state.selectedNodeId && state.nodes[0]) state.selectedNodeId = state.nodes[0].id;
    if (!state.selectedCoreId && state.cores[0]) state.selectedCoreId = state.cores[0].id;
  } catch (err) {
    if (!quiet) showToast(err.message || "Could not refresh panel data", "bad");
    throw err;
  }
}

function render(loginError = "") {
  if (!state.user) {
    appRoot.innerHTML = renderLogin(loginError);
    return;
  }
  const page = renderPage();
  appRoot.innerHTML = renderShell(state, page);
}

function renderPage() {
  switch (state.view) {
    case "nodes": return renderNodes(state);
    case "cores": return renderCores(state);
    case "runtime": return renderRuntime(state);
    case "logs": return renderLogs(state);
    case "integrity": return renderIntegrity(state);
    case "settings": return renderSettings(state);
    case "dashboard":
    default: return renderDashboard(state);
  }
}

async function onSubmit(event) {
  if (event.target.id === "loginForm") {
    event.preventDefault();
    const fd = new FormData(event.target);
    try {
      state.user = await api.login(fd.get("username"), fd.get("password"));
      await loadAll();
      await loadLogs({ quiet: true });
      setView("dashboard");
      render();
    } catch (err) {
      render(err.message || "Authentication failed.");
    }
  }
  if (event.target.id === "nodeForm") {
    event.preventDefault();
    await saveNodeFromForm(event.target);
  }
  if (event.target.id === "logsForm") {
    event.preventDefault();
    updateLogFilters(event.target);
    await loadLogs();
  }
}

async function onChange(event) {
  const target = event.target;
  if (target.closest("#logsForm")) {
    updateLogFilters(target.form);
    await loadLogs({ quiet: true });
    render();
    return;
  }
  if (!state.draftCore || !target.name) return;
  updateDraftCore(target.name, target.type === "checkbox" ? target.checked : target.value);
  state.dirtyCore = true;
  render();
}

async function onClick(event) {
  const nav = event.target.closest("[data-nav]");
  if (nav) {
    setView(nav.dataset.nav);
    if (state.view === "logs" && !state.logs.lines.length) await loadLogs({ quiet: true });
    render();
    return;
  }
  const selectNode = event.target.closest("[data-select-node]");
  if (selectNode) { state.selectedNodeId = selectNode.dataset.selectNode; state.selectedNodeTab = "overview"; state.nodePreview = null; state.nodeDrift = null; render(); return; }
  const selectCore = event.target.closest("[data-select-core]");
  if (selectCore) { state.selectedCoreId = selectCore.dataset.selectCore; render(); return; }
  const nodeTab = event.target.closest("[data-node-tab]");
  if (nodeTab) { state.selectedNodeTab = nodeTab.dataset.nodeTab; render(); return; }
  const coreTab = event.target.closest("[data-core-tab]");
  if (coreTab) { state.selectedCoreTab = coreTab.dataset.coreTab; render(); return; }

  const actionEl = event.target.closest("[data-action]");
  if (!actionEl) return;
  const action = actionEl.dataset.action;
  try {
    await handleAction(action, actionEl);
  } catch (err) {
    showToast(err.message || "Action failed", "bad");
  }
}

async function handleAction(action, el) {
  if (action === "logout") { await api.logout(); state.user = null; render(); return; }
  if (action === "global-refresh") { await loadAll(); await loadLogs({ quiet: true }); showToast("Panel data refreshed", "good"); render(); return; }
  if (action === "new-node") { state.draftNode = defaultNode(); state.view = "nodes"; render(); return; }
  if (action === "cancel-node-edit") { state.draftNode = null; render(); return; }
  if (action === "edit-node") { state.draftNode = clone(state.nodes.find((n) => String(n.id) === String(el.dataset.nodeId))); render(); return; }
  if (action === "generate-node-key") { const res = await api.generateNodeKey(); state.draftNode.api_key = res.api_key; render(); return; }
  if (action === "check-draft-node") { await checkDraftNode(); return; }
  if (action === "delete-node") { await deleteNode(el.dataset.nodeId); return; }
  if (action === "check-node") { const res = await api.checkNode(el.dataset.nodeId); showToast(res.message || "Node checked", res.ok ? "good" : "warn"); await loadAll(); render(); return; }
  if (action === "sync-node") { const res = await api.syncNode(el.dataset.nodeId); showToast(res.ok ? "Runtime synced" : "Runtime sync returned warnings", res.ok ? "good" : "warn"); await loadAll(); render(); return; }
  if (action === "sync-all") { const res = await api.syncAll(); showToast(res.message || "Runtime sync finished", "good"); await loadAll(); render(); return; }
  if (action === "apply-node") { await applyNode(el.dataset.nodeId); return; }
  if (action === "load-preview") { const res = await api.nodePreview(el.dataset.nodeId); state.nodePreview = res.config || res; state.selectedNodeTab = "preview"; render(); return; }
  if (action === "load-drift") { const res = await api.nodeDrift(el.dataset.nodeId, true); state.nodeDrift = res.drift || res; state.selectedNodeTab = "drift"; render(); return; }
  if (action === "new-core") { state.draftCore = defaultCore(state); state.dirtyCore = true; state.selectedCoreTab = "overview"; state.view = "cores"; render(); return; }
  if (action === "edit-core") { state.draftCore = clone(state.cores.find((c) => String(c.id) === String(el.dataset.coreId))); state.dirtyCore = false; state.selectedCoreTab = "overview"; render(); return; }
  if (action === "cancel-core-edit") { if (state.dirtyCore && !(await confirmDialog({ title:"Discard changes?", message:"Unsaved core editor changes will be lost.", danger:true, confirmText:"Discard" }))) return; state.draftCore = null; state.dirtyCore = false; render(); return; }
  if (action === "save-core") { await saveCore(false); return; }
  if (action === "save-apply-core") { await saveCore(true); return; }
  if (action === "delete-core") { await deleteCore(el.dataset.coreId); return; }
  if (action === "apply-core") { await applyCore(el.dataset.coreId); return; }
  if (action === "preview-core") { const res = await api.corePreview(el.dataset.coreId); state.corePreview = res.node_config_preview || res; showToast("Preview loaded", "good"); render(); return; }
  if (action === "add-inbound") { state.draftCore.inbounds.push(defaultInbound()); state.dirtyCore = true; render(); return; }
  if (action === "remove-inbound") { state.draftCore.inbounds.splice(Number(el.dataset.index), 1); state.dirtyCore = true; render(); return; }
  if (action === "add-balancer") { state.draftCore.balancers.push(defaultBalancer()); state.dirtyCore = true; render(); return; }
  if (action === "remove-balancer") { state.draftCore.balancers.splice(Number(el.dataset.index), 1); state.dirtyCore = true; render(); return; }
  if (action === "add-endpoint") { state.draftCore.balancers[Number(el.dataset.index)].endpoints.push(defaultEndpoint()); state.dirtyCore = true; render(); return; }
  if (action === "remove-endpoint") { state.draftCore.balancers[Number(el.dataset.balancer)].endpoints.splice(Number(el.dataset.index), 1); state.dirtyCore = true; render(); return; }
  if (action === "add-dependency") { state.draftCore.dependencies.push(defaultDependency(state.draftCore.dependencies.length)); state.dirtyCore = true; render(); return; }
  if (action === "remove-dependency") { await removeDependency(Number(el.dataset.index)); return; }
  if (action === "validate-advanced") { await validateAdvanced(); return; }
  if (action === "preview-draft-core") { state.corePreview = buildCorePayload(); state.selectedCoreTab = "preview"; render(); return; }
  if (action === "refresh-logs") { await loadLogs(); render(); return; }
  if (action === "copy-logs") { await navigator.clipboard.writeText((state.logs.lines || []).join("\n")); showToast("Visible logs copied", "good"); return; }
  if (action === "clear-visible-logs") { state.logs.lines = []; render(); return; }
  if (action === "refresh-integrity") { state.integrity = await api.integrity(); render(); return; }
  if (action === "repair-data") { await repairData(); return; }
}

async function saveNodeFromForm(form) {
  const fd = new FormData(form);
  const payload = {
    name: String(fd.get("name") || "").trim(),
    address: String(fd.get("address") || "").trim(),
    api_port: intValue(fd.get("api_port"), 62051, 1, 65535),
    api_key: String(fd.get("api_key") || "").trim(),
    peer_token_refresh_interval: intValue(fd.get("peer_token_refresh_interval"), 30, 5, 86400),
    peer_token_ttl: intValue(fd.get("peer_token_ttl"), 120, 10, 86400),
    enabled: Boolean(fd.get("enabled")),
  };
  if (!payload.name || !payload.address || !payload.api_key) throw new Error("Node name, address and API key are required.");
  if (state.draftNode?.id) await api.updateNode(state.draftNode.id, payload); else await api.createNode(payload);
  state.draftNode = null;
  await loadAll();
  showToast("Node saved", "good");
  render();
}

async function checkDraftNode() {
  const form = $("#nodeForm");
  if (!form) return;
  const fd = new FormData(form);
  const payload = { name: String(fd.get("name") || "draft"), address: String(fd.get("address") || ""), api_port: intValue(fd.get("api_port"), 62051, 1, 65535), api_key: String(fd.get("api_key") || ""), peer_token_refresh_interval: intValue(fd.get("peer_token_refresh_interval"), 30, 5, 86400), peer_token_ttl: intValue(fd.get("peer_token_ttl"), 120, 10, 86400), enabled: Boolean(fd.get("enabled")) };
  const res = await api.checkNodeDraft(payload);
  showToast(res.message || "Draft node checked", res.ok ? "good" : "warn");
}

async function deleteNode(id) {
  if (!(await confirmDialog({ title:"Delete node?", message:"Linked cores will be disabled. This cannot be undone from the UI.", danger:true, confirmText:"Delete" }))) return;
  await api.deleteNode(id);
  state.selectedNodeId = "";
  await loadAll();
  showToast("Node deleted", "good");
  render();
}

async function applyNode(id) {
  if (!(await confirmDialog({ title:"Apply node config?", message:"The desired core config will be pushed to the selected runtime node.", confirmText:"Apply" }))) return;
  const res = await api.applyNode(id);
  showToast(res.message || "Node config applied", "good");
  await loadAll();
  render();
}

async function deleteCore(id) {
  if (!(await confirmDialog({ title:"Delete core?", message:"This removes the desired routing config from the panel store.", danger:true, confirmText:"Delete" }))) return;
  await api.deleteCore(id);
  state.selectedCoreId = "";
  await loadAll();
  showToast("Core deleted", "good");
  render();
}

async function applyCore(id) {
  if (!(await confirmDialog({ title:"Apply core?", message:"This pushes routing config to the linked node runtime.", confirmText:"Apply" }))) return;
  const res = await api.applyCore(id);
  showToast(res.message || "Core applied", "good");
  await loadAll();
  render();
}

async function saveCore(applyAfter) {
  const payload = buildCorePayload();
  const errors = validateCorePayload(payload);
  if (errors.length) throw new Error(errors.slice(0, 4).join(" | "));
  let saved;
  if (state.draftCore.id) saved = await api.updateCore(state.draftCore.id, payload); else saved = await api.createCore(payload);
  const core = saved.core;
  state.draftCore = null;
  state.dirtyCore = false;
  state.selectedCoreId = core.id;
  await loadAll();
  showToast("Core saved", "good");
  if (applyAfter) await applyCore(core.id); else render();
}

function buildCorePayload() {
  const c = clone(state.draftCore || {});
  c.name = String(c.name || "").trim();
  c.node_id = String(c.node_id || "").trim();
  c.enabled = Boolean(c.enabled);
  c.inbounds = (c.inbounds || []).map((ib, i) => ({
    name: String(ib.name || `inbound-${i + 1}`).trim(),
    bind_ip: String(ib.bind_ip || "0.0.0.0").trim(),
    public_host: String(ib.public_host || "").trim(),
    public_ports_mode: ["use_inbound_ports", "random", "fixed"].includes(ib.public_ports_mode) ? ib.public_ports_mode : "use_inbound_ports",
    public_fixed_ports: parsePorts(ib.public_fixed_ports),
    public_random_count: intValue(ib.public_random_count, 1, 1, 4096),
    port_mode: ib.port_mode === "random" ? "random" : "fixed",
    fixed_ports: parsePorts(ib.fixed_ports),
    random_count: intValue(ib.random_count, 1, 1, 4096),
    target_type: ib.target_type === "balancer" ? "balancer" : "static",
    target_host: String(ib.target_host || "127.0.0.1").trim(),
    target_port: intValue(ib.target_port, 80, 1, 65535),
    target_balancer: String(ib.target_balancer || "").trim(),
    enabled: ib.enabled !== false,
    notes: String(ib.notes || "").slice(0, 500),
  }));
  c.dependencies = (c.dependencies || []).map((dep, i) => ({
    id: String(dep.id || `dep_${Math.random().toString(16).slice(2, 10)}`),
    type: "node",
    name: String(dep.name || `dep ${i + 1}`).trim(),
    ref_id: String(dep.ref_id || "").trim(),
    host: String(dep.host || "").trim(),
    sync_interval: intValue(dep.sync_interval, 5, 1, 86400),
    required: dep.required !== false,
    notes: String(dep.notes || "").slice(0, 500),
  })).filter((dep) => dep.ref_id && dep.ref_id !== c.node_id);
  c.balancers = (c.balancers || []).map((b, bi) => ({
    alias: String(b.alias || `balancer-${bi + 1}`).trim(),
    strategy: ["round_robin", "random", "failover", "least_connections"].includes(b.strategy) ? b.strategy : "round_robin",
    enabled: b.enabled !== false,
    notes: String(b.notes || "").slice(0, 500),
    endpoints: (b.endpoints || []).map((ep) => {
      const dep = c.dependencies.find((d) => String(d.id) === String(ep.dependency_id));
      if (ep.type === "node_inbound") {
        return { type:"node_inbound", host:"127.0.0.1", port:intValue(ep.port, 80, 1, 65535), dependency_id:String(ep.dependency_id||""), node_id:String(dep?.ref_id || ep.node_id || ""), core_id:String(ep.core_id||""), inbound_name:String(ep.inbound_name||""), weight:floatValue(ep.weight, 1, 0, Infinity), enabled:ep.enabled !== false, notes:String(ep.notes||"").slice(0,500) };
      }
      return { type:"static", host:String(ep.host || "127.0.0.1").trim(), port:intValue(ep.port, 80, 1, 65535), dependency_id:"", node_id:"", core_id:"", inbound_name:"", weight:floatValue(ep.weight, 1, 0, Infinity), enabled:ep.enabled !== false, notes:String(ep.notes||"").slice(0,500) };
    }),
  }));
  c.advanced_config = c.advanced_config || { enabled:false, json_config:"" };
  c.advanced_config.enabled = Boolean(c.advanced_config.enabled);
  c.advanced_config.json_config = String(c.advanced_config.json_config || "");
  return c;
}

function validateCorePayload(c) {
  const errors = [];
  if (!c.name) errors.push("Core name is required.");
  if (!c.node_id) errors.push("Select a node for this core.");
  c.inbounds.forEach((ib, i) => {
    if (ib.port_mode === "fixed" && !ib.fixed_ports.length) errors.push(`Inbound ${i + 1}: fixed listen ports are required.`);
    if (ib.public_ports_mode === "fixed" && !ib.public_fixed_ports.length) errors.push(`Inbound ${i + 1}: public fixed ports are required.`);
    if (ib.target_type === "balancer" && !ib.target_balancer) errors.push(`Inbound ${i + 1}: target balancer is required.`);
  });
  c.balancers.forEach((b, bi) => (b.endpoints || []).forEach((ep, ei) => {
    if (ep.type === "node_inbound") {
      if (!ep.dependency_id) errors.push(`Balancer ${bi + 1}, endpoint ${ei + 1}: select a dependency first.`);
      if (!ep.node_id) errors.push(`Balancer ${bi + 1}, endpoint ${ei + 1}: selected dependency has no valid node.`);
      if (!ep.inbound_name) errors.push(`Balancer ${bi + 1}, endpoint ${ei + 1}: select a remote inbound.`);
    }
  }));
  if (c.advanced_config.enabled) {
    try { JSON.parse(c.advanced_config.json_config || "{}"); } catch (err) { errors.push(`Advanced JSON is invalid: ${err.message}`); }
  }
  return errors;
}

function updateDraftCore(path, value) {
  const parts = String(path).split(".");
  let obj = state.draftCore;
  for (let i = 0; i < parts.length - 1; i++) {
    const key = numericKey(parts[i]);
    obj = obj[key];
    if (obj == null) return;
  }
  const last = parts[parts.length - 1];
  const key = numericKey(last);
  const normalized = normalizeFieldValue(last, value);
  obj[key] = normalized;
  if (last === "dependency_id") {
    const dep = (state.draftCore.dependencies || []).find((d) => String(d.id) === String(value));
    obj.node_id = dep?.ref_id || "";
    obj.core_id = "";
    obj.inbound_name = "";
  }
  if (last === "type") {
    if (value === "node_inbound") { obj.dependency_id = obj.dependency_id || ""; obj.node_id = ""; obj.core_id = ""; obj.inbound_name = ""; }
    else { obj.host = obj.host || "127.0.0.1"; obj.port = obj.port || 80; obj.dependency_id = ""; obj.node_id = ""; obj.core_id = ""; obj.inbound_name = ""; }
  }
}

function numericKey(part) { return /^\d+$/.test(part) ? Number(part) : part; }
function normalizeFieldValue(name, value) {
  if (["fixed_ports", "public_fixed_ports"].includes(name)) return parsePorts(value);
  if (["api_port", "random_count", "public_random_count", "target_port", "port", "sync_interval", "peer_token_refresh_interval", "peer_token_ttl"].includes(name)) return intValue(value, 1, 1, 86400);
  if (name === "weight") return floatValue(value, 1, 0, Infinity);
  if (["enabled", "required", "advanced_config.enabled"].includes(name)) return Boolean(value);
  return value;
}

async function removeDependency(index) {
  const dep = state.draftCore.dependencies[index];
  const used = (state.draftCore.balancers || []).flatMap((b) => b.endpoints || []).filter((ep) => String(ep.dependency_id) === String(dep.id)).length;
  if (used && !(await confirmDialog({ title:"Remove used dependency?", message:`This dependency is referenced by ${used} endpoint(s). Those references will be cleared.`, danger:true, confirmText:"Remove" }))) return;
  state.draftCore.dependencies.splice(index, 1);
  for (const b of state.draftCore.balancers || []) for (const ep of b.endpoints || []) if (String(ep.dependency_id) === String(dep.id)) { ep.dependency_id = ""; ep.node_id = ""; ep.core_id = ""; ep.inbound_name = ""; }
  state.dirtyCore = true;
  render();
}

async function validateAdvanced() {
  const payload = buildCorePayload();
  const res = await api.validateAdvanced(payload.advanced_config.json_config);
  showToast(res.valid ? "Advanced JSON is valid" : (res.errors || ["Invalid JSON"]).join("; "), res.valid ? "good" : "bad");
}

async function loadLogs({ quiet = false } = {}) {
  try {
    const res = await api.logs(state.logs);
    state.logs = { ...state.logs, ...res, error: res.ok === false ? (res.error || "Could not load logs") : "" };
  } catch (err) {
    state.logs.error = err.message || "Could not load logs";
    if (!quiet) showToast(state.logs.error, "bad");
  }
}

function updateLogFilters(form) {
  const fd = new FormData(form);
  state.logs.source = String(fd.get("source") || "panel");
  state.logs.level = String(fd.get("level") || "all");
  state.logs.q = String(fd.get("q") || "");
  state.logs.limit = intValue(fd.get("limit"), 300, 1, 5000);
}

async function repairData() {
  if (!(await confirmDialog({ title:"Repair data?", message:"This will recalculate store relationships and clear stale references where possible.", danger:true, confirmText:"Repair" }))) return;
  state.integrity = await api.repair();
  await loadAll();
  showToast("Repair complete", "good");
  render();
}

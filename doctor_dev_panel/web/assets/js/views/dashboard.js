import { badge, emptyState, healthDots, metric, panel } from "../core/components.js";
import { escapeHtml, nodeName, relativeTime } from "../core/utils.js";

export function renderDashboard(state) {
  const s = state.stats || { nodes: {}, cores: {}, inbounds: {}, balancers: {} };
  if (!state.nodes.length) {
    return emptyState("No nodes configured", "Add your first routing node before creating cores or runtime routes.", `<button class="btn primary" data-action="new-node">Add First Node</button>`, "nodes");
  }
  const metrics = `<div class="grid cols-4">
    ${metric("Total Nodes", s.nodes?.total ?? 0, "configured control-plane nodes")}
    ${metric("Running Nodes", s.nodes?.running ?? 0, "healthy node checks", "good")}
    ${metric("Error Nodes", s.nodes?.error ?? 0, "nodes needing attention", (s.nodes?.error || 0) ? "bad" : "")}
    ${metric("Runtime Drift", driftCount(state), "detected warnings", driftCount(state) ? "warn" : "good")}
    ${metric("Total Cores", s.cores?.total ?? 0, `${s.cores?.enabled ?? 0} enabled`)}
    ${metric("Enabled Inbounds", s.inbounds?.enabled ?? 0, `${s.inbounds?.total ?? 0} total`)}
    ${metric("Balancers", s.balancers?.total ?? 0, "routing groups")}
    ${metric("Disabled Nodes", s.nodes?.disabled ?? 0, "excluded from operations", (s.nodes?.disabled || 0) ? "warn" : "")}
  </div>`;
  return `${metrics}${panel("Runtime Health Matrix", runtimeTable(state), `<button class="btn small" data-action="sync-all">Sync All Runtime</button>`)}${panel("Recent Issues", recentIssues(state))}${panel("Quick Actions", `<div class="toolbar"><button class="btn primary" data-action="new-node">Add Node</button><button class="btn" data-action="new-core">Add Core</button><button class="btn" data-nav="logs">Open Logs</button><button class="btn" data-nav="integrity">Integrity Check</button></div>`)}`;
}

function runtimeTable(state) {
  const rows = state.nodes.map((node) => {
    const rt = state.runtimeCache?.nodes?.[node.id] || {};
    const api = rt.api || {};
    return `<tr data-node-row="${escapeHtml(node.id)}"><td><strong>${escapeHtml(node.name)}</strong><br><span class="muted mono">${escapeHtml(node.id)}</span></td><td class="mono">${escapeHtml(node.address)}:${escapeHtml(node.api_port)}</td><td>${healthDots({ reachable: rt.reachable, auth: rt.auth_ok, runtime: rt.runtime_ok })}</td><td>${badge(node.status || "pending")}</td><td>${escapeHtml(rt.listeners?.length ?? rt.summary?.listeners_total ?? 0)}</td><td class="mono">${escapeHtml(api.api_port || api.port || "—")}</td><td>${escapeHtml(relativeTime(rt.last_seen_at || node.last_checked_at))}</td><td class="muted">${escapeHtml(rt.last_error || node.last_error || "")}</td></tr>`;
  }).join("");
  return `<div class="table-wrap"><table><thead><tr><th>Node</th><th>Address</th><th>Health</th><th>Status</th><th>Listeners</th><th>Runtime API</th><th>Last Seen</th><th>Error</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function recentIssues(state) {
  const issues = [];
  for (const node of state.nodes) {
    const rt = state.runtimeCache?.nodes?.[node.id] || {};
    if (node.last_error) issues.push(["bad", `${node.name}: ${node.last_error}`, "node check"]);
    if (rt.last_error) issues.push(["bad", `${node.name}: ${rt.last_error}`, "runtime"]);
    const peerErrors = rt.summary?.peer_sync_errors || {};
    for (const msg of Object.values(peerErrors)) issues.push(["warn", `${node.name}: ${msg}`, "peer sync"]);
  }
  if (!issues.length) return `<div class="notice good">No recent runtime or node issues detected.</div>`;
  return `<div class="grid">${issues.slice(0, 8).map(([kind, msg, area]) => `<div class="notice ${kind}"><strong>${escapeHtml(area)}</strong><br>${escapeHtml(msg)}</div>`).join("")}</div>`;
}

function driftCount(state) {
  let count = 0;
  for (const node of state.nodes) {
    const rt = state.runtimeCache?.nodes?.[node.id] || {};
    if (rt.last_error || rt.runtime_ok === false || rt.auth_ok === false || rt.reachable === false) count += 1;
  }
  return count;
}

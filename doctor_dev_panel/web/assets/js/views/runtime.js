import { badge, emptyState, jsonBlock, panel } from "../core/components.js";
import { escapeHtml, nodeName, relativeTime } from "../core/utils.js";

export function renderRuntime(state) {
  if (!state.nodes.length) return emptyState("No runtime data", "Add and sync nodes before troubleshooting runtime state.", `<button class="btn primary" data-nav="nodes">Open Nodes</button>`, "runtime");
  return `${panel("Runtime Overview", overviewTable(state), `<button class="btn small" data-action="sync-all">Sync All Runtime</button>`)}${panel("Listeners", listenerTable(state))}${panel("Advertised Inbounds", advertisedTable(state))}${panel("Peer Sync Errors", peerErrors(state))}`;
}

function overviewTable(state) {
  const rows = state.nodes.map((n) => {
    const rt = state.runtimeCache?.nodes?.[n.id] || {};
    const core = rt.core || rt.summary?.core || {};
    return `<tr><td><strong>${escapeHtml(n.name)}</strong><br><span class="muted mono">${escapeHtml(n.id)}</span></td><td>${badge(rt.reachable ? "reachable" : "unreachable", rt.reachable ? "good" : "bad")}</td><td>${badge(rt.auth_ok ? "auth ok" : "auth issue", rt.auth_ok ? "good" : "warn")}</td><td>${badge(rt.runtime_ok ? "runtime ok" : "runtime issue", rt.runtime_ok ? "good" : "warn")}</td><td>${escapeHtml(core.name || "—")}</td><td>${escapeHtml(rt.listeners?.length ?? rt.summary?.listeners_total ?? 0)}</td><td>${escapeHtml(relativeTime(rt.last_success_at || rt.synced_at))}</td></tr>`;
  }).join("");
  return `<div class="table-wrap"><table><thead><tr><th>Node</th><th>Reach</th><th>Auth</th><th>Runtime</th><th>Core</th><th>Listeners</th><th>Last Sync</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function listenerTable(state) {
  const rows = [];
  for (const n of state.nodes) {
    const rt = state.runtimeCache?.nodes?.[n.id] || {};
    for (const l of rt.listeners || rt.summary?.listeners || []) rows.push(`<tr><td>${escapeHtml(n.name)}</td><td>${escapeHtml(l.core_name || l.core_id)}</td><td>${escapeHtml(l.inbound_name)}</td><td class="mono">${escapeHtml(l.bind_ip)}:${escapeHtml(l.requested_port)}</td><td class="mono">${escapeHtml(l.port || "—")}</td><td>${badge(l.status || "unknown")}</td></tr>`);
  }
  if (!rows.length) return `<p class="muted">No listeners in runtime cache.</p>`;
  return `<div class="table-wrap"><table><thead><tr><th>Node</th><th>Core</th><th>Inbound</th><th>Requested</th><th>Actual</th><th>Status</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}

function advertisedTable(state) {
  const rows = [];
  for (const n of state.nodes) {
    const rt = state.runtimeCache?.nodes?.[n.id] || {};
    for (const a of rt.summary?.advertised_inbounds || []) rows.push(`<tr><td>${escapeHtml(n.name)}</td><td>${escapeHtml(a.core_name || a.core_id)}</td><td>${escapeHtml(a.inbound_name)}</td><td class="mono">${escapeHtml(a.public_host || n.address || "fallback")}</td><td>${badge(a.public_ports_mode || "use_inbound_ports")}</td><td class="mono">${escapeHtml((a.public_ports || []).join(", ") || "—")}</td><td>${badge(a.status || "advertised")}</td></tr>`);
  }
  if (!rows.length) return `<p class="muted">No advertised public routes in runtime cache.</p>`;
  return `<div class="table-wrap"><table><thead><tr><th>Node</th><th>Core</th><th>Inbound</th><th>Public Host</th><th>Mode</th><th>Public Ports</th><th>Status</th></tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}

function peerErrors(state) {
  const rows = [];
  for (const n of state.nodes) {
    const errors = state.runtimeCache?.nodes?.[n.id]?.summary?.peer_sync_errors || {};
    for (const [key, msg] of Object.entries(errors)) rows.push(`<div class="notice bad"><strong>${escapeHtml(n.name)}</strong><br><span class="mono">${escapeHtml(key)}</span><br>${escapeHtml(msg)}</div>`);
  }
  return rows.length ? `<div class="grid">${rows.join("")}</div>` : `<div class="notice good">No peer sync errors in runtime cache.</div>`;
}

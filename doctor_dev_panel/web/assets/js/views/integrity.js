import { badge, jsonBlock } from "../core/components.js";
import { escapeHtml } from "../core/utils.js";

export function renderIntegrity(state) {
  const data = state.integrity || {};
  const issues = data.issues || data.errors || [];
  const healthy = !issues.length;
  return `<section class="panel-card ${healthy ? "" : "danger-zone"}"><div class="card-title-row"><div><h2>System Integrity</h2><p class="muted">Store relationships, stale references and repairable issues.</p></div>${badge(healthy ? "healthy" : "issues", healthy ? "good" : "bad")}</div><div class="grid">${healthy ? `<div class="notice good">No integrity issues detected.</div>` : issues.map((x) => `<div class="notice bad"><strong>${escapeHtml(x.code || x.area || "Issue")}</strong><br>${escapeHtml(x.message || JSON.stringify(x))}</div>`).join("")}<div class="toolbar"><button class="btn" data-action="refresh-integrity">Refresh</button><button class="btn danger" data-action="repair-data">Repair Data</button></div>${jsonBlock(data)}</div></section>`;
}

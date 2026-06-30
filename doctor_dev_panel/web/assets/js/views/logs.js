import { escapeHtml } from "../core/utils.js";

export function renderLogs(state) {
  const log = state.logs || {};
  const sources = (state.logSources || []).map((s) => `<option value="${escapeHtml(s.id)}" ${s.id === log.source ? "selected" : ""}>${escapeHtml(s.label || s.id)}</option>`).join("");
  const lines = (log.lines || []).map((line) => `<span class="log-line ${levelClass(line)}">${escapeHtml(line)}</span>`).join("");
  return `<section class="panel-card"><div class="toolbar between"><h2>Logs</h2><div class="toolbar"><button class="btn small" data-action="refresh-logs">Refresh</button><button class="btn small" data-action="copy-logs">Copy Visible</button><button class="btn small" data-action="clear-visible-logs">Clear Visible</button></div></div><form id="logsForm" class="form-grid four"><div class="form-grid three"><label class="field"><span>Source</span><select class="select" name="source">${sources}</select></label><label class="field"><span>Level</span><select class="select" name="level">${["all","debug","info","warning","error"].map((x) => `<option ${x === log.level ? "selected" : ""}>${x}</option>`).join("")}</select></label><label class="field"><span>Limit</span><input class="input" type="number" min="1" max="5000" name="limit" value="${escapeHtml(log.limit || 300)}"></label></div><label class="field"><span>Search</span><input class="input" name="q" value="${escapeHtml(log.q || "")}" placeholder="filter text"></label></form>${log.error ? `<div class="notice bad">${escapeHtml(log.error)}</div>` : ""}<div class="muted">${escapeHtml((log.lines || []).length)} lines · ${escapeHtml(log.path || log.source || "")}</div><pre class="log-box">${lines || "No logs found for this filter."}</pre></section>`;
}

function levelClass(line) {
  const t = String(line).toLowerCase();
  if (t.includes("| error |") || t.includes(" error ")) return "error";
  if (t.includes("| warning |") || t.includes(" warn")) return "warning";
  if (t.includes("| debug |") || t.includes(" debug ")) return "debug";
  return "info";
}

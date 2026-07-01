import { escapeHtml } from "../core/utils.js";

export function renderLogs(state) {
  const log = state.logs || {};
  const sources = (state.logSources || []).map((s) => `<option value="${escapeHtml(s.id)}" ${s.id === log.source ? "selected" : ""}>${escapeHtml(s.label || s.id)}</option>`).join("");
  const visible = visibleLogLines(log);
  const total = (log.allLines || log.lines || []).length;
  const meta = total === visible.length ? `${visible.length} lines` : `${visible.length} / ${total} lines`;
  return `<section class="panel-card"><div class="toolbar between"><h2>Logs</h2><div class="toolbar"><button class="btn small" data-action="refresh-logs">Refresh</button><button class="btn small" data-action="copy-logs">Copy Visible</button><button class="btn small" data-action="clear-visible-logs">Clear Visible</button></div></div><form id="logsForm" class="form-grid four"><div class="form-grid three"><label class="field"><span>Source</span><select class="select" name="source">${sources}</select></label><label class="field"><span>Level</span><select class="select" name="level">${["all","debug","info","warning","error"].map((x) => `<option ${x === log.level ? "selected" : ""}>${x}</option>`).join("")}</select></label><label class="field"><span>Limit</span><input class="input" type="number" min="1" max="5000" name="limit" value="${escapeHtml(log.limit || 300)}"></label></div><label class="field"><span>Search</span><input class="input" name="q" value="${escapeHtml(log.q || "")}" placeholder="live filter current logs" autocomplete="off"></label></form>${log.error ? `<div class="notice bad">${escapeHtml(log.error)}</div>` : ""}<div class="muted" id="logMeta">${escapeHtml(meta)} · ${escapeHtml(log.path || log.source || "")}</div><pre class="log-box" id="logBox">${renderLogLines(visible) || "No logs found for this filter."}</pre></section>`;
}

export function visibleLogLines(log = {}) {
  const q = String(log.q || "").trim().toLowerCase();
  const lines = Array.isArray(log.allLines) && log.allLines.length ? log.allLines : (log.lines || []);
  if (!q) return lines;
  return lines.filter((line) => String(line).toLowerCase().includes(q));
}

export function renderLogLines(lines = []) {
  return (lines || []).map((line) => `<span class="log-line ${levelClass(line)}">${renderLogLine(line)}</span>`).join("");
}

function renderLogLine(line) {
  const raw = String(line ?? "");
  const level = levelClass(raw);
  const match = raw.match(/\b(CRITICAL|ERROR|WARNING|WARN|INFO|DEBUG)\b/i);
  if (!match || match.index === undefined) return escapeHtml(raw);
  const before = raw.slice(0, match.index);
  const token = match[0].toUpperCase();
  const after = raw.slice(match.index + match[0].length);
  return `<span class="log-prefix ${level}">${escapeHtml(before)}</span><span class="log-level-token ${level}">${escapeHtml(token)}</span>${escapeHtml(after)}`;
}

function levelClass(line) {
  const t = String(line).toLowerCase();
  if (t.includes("| critical |") || t.includes(" critical ") || t.includes("| error |") || t.includes(" error ")) return "error";
  if (t.includes("| warning |") || t.includes(" warning ") || t.includes("| warn |") || t.includes(" warn ")) return "warning";
  if (t.includes("| debug |") || t.includes(" debug ")) return "debug";
  return "info";
}

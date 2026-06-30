export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[ch]));
}

export function clone(value) {
  return JSON.parse(JSON.stringify(value ?? null));
}

export function nowLabel() {
  return new Date().toLocaleTimeString();
}

export function relativeTime(value) {
  if (!value) return "never";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const diff = Math.round((Date.now() - d.getTime()) / 1000);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return d.toLocaleString();
}

export function parsePorts(value) {
  const raw = Array.isArray(value) ? value : String(value ?? "").split(",");
  const ports = [];
  for (const item of raw) {
    const n = Number.parseInt(String(item).trim(), 10);
    if (Number.isInteger(n) && n >= 1 && n <= 65535 && !ports.includes(n)) ports.push(n);
  }
  return ports;
}

export function portsText(value) {
  const ports = parsePorts(value);
  return ports.join(",");
}

export function intValue(value, fallback, min, max) {
  let n = Number.parseInt(String(value ?? ""), 10);
  if (!Number.isFinite(n)) n = fallback;
  if (Number.isFinite(min)) n = Math.max(min, n);
  if (Number.isFinite(max)) n = Math.min(max, n);
  return n;
}

export function floatValue(value, fallback, min, max) {
  let n = Number.parseFloat(String(value ?? ""));
  if (!Number.isFinite(n)) n = fallback;
  if (Number.isFinite(min)) n = Math.max(min, n);
  if (Number.isFinite(max)) n = Math.min(max, n);
  return n;
}

export function nodeById(state, id) {
  return (state.nodes || []).find((n) => String(n.id) === String(id));
}

export function coreById(state, id) {
  return (state.cores || []).find((c) => String(c.id) === String(id));
}

export function nodeName(state, id) {
  const node = nodeById(state, id);
  return node ? (node.name || node.address || node.id) : (id || "missing node");
}

export function coreName(state, id) {
  const core = coreById(state, id);
  return core ? (core.name || core.id) : (id || "missing core");
}

export function statusKind(value) {
  const v = String(value || "").toLowerCase();
  if (["ok", "running", "healthy", "applied", "ready", "true"].includes(v)) return "good";
  if (["warning", "warn", "pending", "drift", "stale"].includes(v)) return "warn";
  if (["error", "failed", "false", "missing", "unreachable"].includes(v)) return "bad";
  if (["disabled", "inactive"].includes(v)) return "disabled";
  return "blue";
}

export function firstCoreForNode(state, nodeId) {
  return (state.cores || []).find((c) => String(c.node_id || "") === String(nodeId || ""));
}

export function catalogForNode(state, nodeId) {
  return (state.inboundCatalog || []).filter((item) => String(item.node_id || "") === String(nodeId || ""));
}

export function groupBy(list, keyFn) {
  return (list || []).reduce((acc, item) => {
    const key = keyFn(item);
    (acc[key] ||= []).push(item);
    return acc;
  }, {});
}

export function downloadText(filename, text) {
  const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

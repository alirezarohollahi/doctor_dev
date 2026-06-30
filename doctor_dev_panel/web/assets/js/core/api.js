export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.status = status;
    this.payload = payload;
  }
}

async function request(path, options = {}) {
  const opts = { credentials: "same-origin", headers: { Accept: "application/json" }, ...options };
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers = { ...opts.headers, "Content-Type": "application/json" };
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, opts);
  const type = res.headers.get("content-type") || "";
  const payload = type.includes("json") ? await res.json().catch(() => ({})) : await res.text();
  if (!res.ok) {
    const detail = payload && typeof payload === "object" ? (payload.detail?.message || payload.detail || payload.message) : payload;
    throw new ApiError(typeof detail === "string" ? detail : `Request failed: ${res.status}`, res.status, payload);
  }
  return payload;
}

export const api = {
  get: (path) => request(path),
  post: (path, body = undefined) => request(path, { method: "POST", body }),
  put: (path, body) => request(path, { method: "PUT", body }),
  del: (path) => request(path, { method: "DELETE" }),
  authMe: () => request("/api/auth/me"),
  login: (username, password) => request("/api/auth/login", { method: "POST", body: { username, password } }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  summary: () => request("/api/panel/summary"),
  stats: () => request("/api/panel/stats"),
  integrity: () => request("/api/panel/integrity"),
  repair: () => request("/api/panel/repair", { method: "POST" }),
  nodes: () => request("/api/nodes"),
  createNode: (body) => request("/api/nodes", { method: "POST", body }),
  updateNode: (id, body) => request(`/api/nodes/${encodeURIComponent(id)}`, { method: "PUT", body }),
  deleteNode: (id) => request(`/api/nodes/${encodeURIComponent(id)}`, { method: "DELETE" }),
  generateNodeKey: () => request("/api/nodes/api-key", { method: "POST" }),
  checkNode: (id) => request(`/api/nodes/${encodeURIComponent(id)}/check`, { method: "POST" }),
  checkNodeDraft: (body) => request("/api/nodes/check", { method: "POST", body }),
  syncNode: (id) => request(`/api/nodes/${encodeURIComponent(id)}/sync-runtime`, { method: "POST" }),
  syncAll: () => request("/api/nodes/sync-runtime", { method: "POST" }),
  nodeRuntime: (id, refresh = false) => request(`/api/nodes/${encodeURIComponent(id)}/runtime?refresh=${refresh ? "true" : "false"}`),
  nodeDrift: (id, refresh = false) => request(`/api/nodes/${encodeURIComponent(id)}/drift?refresh=${refresh ? "true" : "false"}`),
  nodePreview: (id) => request(`/api/nodes/${encodeURIComponent(id)}/config-preview`),
  applyNode: (id) => request(`/api/nodes/${encodeURIComponent(id)}/apply-config`, { method: "POST" }),
  nodeInbounds: (id) => request(`/api/nodes/${encodeURIComponent(id)}/inbounds`),
  runtimeCache: () => request("/api/nodes/runtime-cache"),
  cores: () => request("/api/cores"),
  createCore: (body) => request("/api/cores", { method: "POST", body }),
  updateCore: (id, body) => request(`/api/cores/${encodeURIComponent(id)}`, { method: "PUT", body }),
  deleteCore: (id) => request(`/api/cores/${encodeURIComponent(id)}`, { method: "DELETE" }),
  corePreview: (id) => request(`/api/cores/${encodeURIComponent(id)}/preview`),
  applyCore: (id) => request(`/api/cores/${encodeURIComponent(id)}/apply`, { method: "POST" }),
  validateAdvanced: (json_config) => request("/api/cores/advanced/validate", { method: "POST", body: { json_config } }),
  logSources: () => request("/api/logs/sources"),
  logs: ({ source = "panel", level = "all", q = "", limit = 300 }) => request(`/api/logs?source=${encodeURIComponent(source)}&level=${encodeURIComponent(level)}&q=${encodeURIComponent(q)}&limit=${encodeURIComponent(limit)}`),
};

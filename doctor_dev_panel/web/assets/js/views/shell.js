import { icon } from "../core/components.js";
import { escapeHtml } from "../core/utils.js";

const navGroups = [
  ["Operate", [["dashboard", "Dashboard", "dashboard"], ["nodes", "Nodes", "nodes"], ["cores", "Cores / Routing", "cores"]]],
  ["Observe", [["runtime", "Runtime & Drift", "runtime"], ["logs", "Logs", "logs"], ["integrity", "Integrity / Repair", "integrity"]]],
  ["Account", [["settings", "Settings / Account", "settings"]]],
];

export function renderShell(state, pageHtml) {
  const nav = navGroups.map(([label, items]) => `<div class="nav-group-label">${label}</div>${items.map(([id, name, ico]) => `<button class="nav-item ${state.view === id ? "active" : ""}" data-nav="${id}">${icon(ico)}<span class="nav-text">${name}</span></button>`).join("")}`).join("");
  const stats = state.stats?.nodes || {};
  return `<div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-top"><div class="brand-row"><div class="logo-box">DD</div><div class="brand-name">Doctor Dev</div></div><span class="env-pill">Control Panel</span></div>
      <nav class="nav">${nav}</nav>
      <div class="sidebar-bottom"><div class="health-dots"><span class="dot good"></span><span class="dot ${stats.error ? "bad" : stats.pending ? "warn" : "good"}"></span><span class="dot ${stats.disabled ? "warn" : "good"}"></span></div><small>${stats.running || 0} running · ${stats.error || 0} error · ${stats.disabled || 0} disabled</small></div>
    </aside>
    <section class="main">
      <header class="topbar"><div><h1 class="page-title">${pageTitle(state.view)}</h1><div class="breadcrumb">Doctor Dev / ${escapeHtml(pageTitle(state.view))}</div></div><div class="top-actions"><span class="muted">Last refresh: ${escapeHtml(state.lastRefresh || "never")}</span><button class="btn small" data-action="global-refresh">${icon("refresh")} Refresh</button><button class="btn small ghost" data-nav="settings">${escapeHtml(state.user?.username || "admin")}</button><button class="btn small danger" data-action="logout">Logout</button></div></header>
      <main class="content"><div class="container">${pageHtml}</div></main>
    </section>
  </div>`;
}

export function pageTitle(view) {
  return ({ dashboard: "Dashboard", nodes: "Nodes", cores: "Cores / Routing", runtime: "Runtime & Drift", logs: "Logs", integrity: "Integrity / Repair", settings: "Settings / Account" })[view] || "Dashboard";
}

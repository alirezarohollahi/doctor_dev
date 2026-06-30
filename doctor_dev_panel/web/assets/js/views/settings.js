import { badge, jsonBlock } from "../core/components.js";
import { escapeHtml } from "../core/utils.js";

export function renderSettings(state) {
  return `<section class="panel-card"><h2>Settings / Account</h2><div class="grid cols-2"><dl class="kv"><dt>Admin</dt><dd>${escapeHtml(state.user?.username || "admin")}</dd><dt>Session</dt><dd>${badge("active", "good")}</dd><dt>Panel</dt><dd>${badge("online", "good")}</dd></dl><div class="toolbar"><button class="btn danger" data-action="logout">Logout</button></div></div>${jsonBlock({ nodes: state.nodes.length, cores: state.cores.length, lastRefresh: state.lastRefresh })}</section>`;
}

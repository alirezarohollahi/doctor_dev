import { escapeHtml, statusKind } from "./utils.js";

export function icon(name) {
  const map = { dashboard:"▦", nodes:"◈", cores:"⟡", runtime:"≋", logs:"☰", integrity:"⚕", settings:"⚙", plus:"+", refresh:"⟳", check:"✓", trash:"×", edit:"✎", apply:"↯", copy:"⧉", warn:"!", link:"↗" };
  return `<span class="nav-ico" aria-hidden="true">${map[name] || "•"}</span>`;
}

export function badge(value, kind = "") {
  const k = kind || statusKind(value);
  return `<span class="badge ${escapeHtml(k)}">${escapeHtml(value || "unknown")}</span>`;
}

export function healthDots({ reachable, auth, runtime } = {}) {
  const dot = (v) => `<span class="dot ${v === true ? "good" : v === false ? "bad" : "warn"}"></span>`;
  return `<span class="health-dots" title="reach / auth / runtime">${dot(reachable)}${dot(auth)}${dot(runtime)}</span>`;
}

export function emptyState(title, body, actionHtml = "", ico = "nodes") {
  return `<section class="empty-state"><div class="empty-icon">${icon(ico)}</div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(body)}</p>${actionHtml}</section>`;
}

export function metric(label, value, foot = "", kind = "") {
  return `<article class="card metric ${escapeHtml(kind)}"><label>${escapeHtml(label)}</label><strong>${escapeHtml(value)}</strong><small>${escapeHtml(foot)}</small></article>`;
}

export function panel(title, body, actions = "") {
  return `<section class="panel-card"><div class="card-title-row"><h2>${escapeHtml(title)}</h2><div class="toolbar">${actions}</div></div>${body}</section>`;
}

export function field(label, name, value = "", attrs = "", help = "") {
  return `<label class="field"><span>${escapeHtml(label)}</span><input class="input" name="${escapeHtml(name)}" value="${escapeHtml(value)}" ${attrs}>${help ? `<small>${escapeHtml(help)}</small>` : ""}</label>`;
}

export function numberField(label, name, value = "", attrs = "", help = "") {
  return field(label, name, value, `type="number" ${attrs}`, help);
}

export function textArea(label, name, value = "", attrs = "", help = "") {
  return `<label class="field"><span>${escapeHtml(label)}</span><textarea class="textarea" name="${escapeHtml(name)}" ${attrs}>${escapeHtml(value)}</textarea>${help ? `<small>${escapeHtml(help)}</small>` : ""}</label>`;
}

export function selectField(label, name, options, selected = "", help = "") {
  const html = (options || []).map((opt) => {
    const value = typeof opt === "object" ? opt.value : opt;
    const text = typeof opt === "object" ? opt.label : opt;
    return `<option value="${escapeHtml(value)}" ${String(value) === String(selected) ? "selected" : ""}>${escapeHtml(text)}</option>`;
  }).join("");
  return `<label class="field"><span>${escapeHtml(label)}</span><select class="select" name="${escapeHtml(name)}">${html}</select>${help ? `<small>${escapeHtml(help)}</small>` : ""}</label>`;
}

export function boolField(label, name, checked = false, help = "") {
  return `<label class="field"><span>${escapeHtml(label)}</span><span class="inline-row"><input type="checkbox" name="${escapeHtml(name)}" ${checked ? "checked" : ""}> <span>${checked ? "Enabled" : "Disabled"}</span></span>${help ? `<small>${escapeHtml(help)}</small>` : ""}</label>`;
}

export function jsonBlock(value) {
  const text = typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2);
  return `<pre class="json-box">${escapeHtml(text)}</pre>`;
}

export function issue(title, detail, kind = "warn") {
  return `<div class="notice ${kind}"><strong>${escapeHtml(title)}</strong><br><span>${escapeHtml(detail)}</span></div>`;
}

export function modal(title, body, actions) {
  return `<div class="modal-card"><div class="modal-head"><h3>${escapeHtml(title)}</h3><button class="btn ghost small" data-modal-close>Close</button></div>${body}<div class="modal-actions">${actions}</div></div>`;
}

export function showToast(message, kind = "") {
  const root = document.getElementById("toastRoot");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  root.appendChild(el);
  setTimeout(() => el.remove(), 4500);
}

export function openModal(html) {
  const root = document.getElementById("modalRoot");
  root.innerHTML = html;
  root.classList.remove("hidden");
}

export function closeModal() {
  const root = document.getElementById("modalRoot");
  root.classList.add("hidden");
  root.innerHTML = "";
}

export function confirmDialog({ title = "Confirm action", message = "Continue?", confirmText = "Confirm", danger = false } = {}) {
  return new Promise((resolve) => {
    openModal(modal(title, `<p class="secondary">${escapeHtml(message)}</p>`, `<button class="btn ghost" data-confirm="no">Cancel</button><button class="btn ${danger ? "danger" : "primary"}" data-confirm="yes">${escapeHtml(confirmText)}</button>`));
    const root = document.getElementById("modalRoot");
    const done = (value) => { closeModal(); resolve(value); };
    root.querySelector('[data-confirm="no"]').addEventListener("click", () => done(false));
    root.querySelector('[data-confirm="yes"]').addEventListener("click", () => done(true));
  });
}

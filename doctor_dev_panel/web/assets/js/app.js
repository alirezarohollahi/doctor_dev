"use strict";

// ============================================================
// 1. UTILITIES
// ============================================================

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const UI_TEXT = Object.freeze({
  invalidNode: "This node has invalid saved data. Refresh the page or run Repair Data.",
  invalidCore: "This core has invalid saved data. Refresh the page or run Repair Data.",
  unknownNode: "Unlinked node",
  missingNode: "Missing linked node",
  notApplied: "Not applied yet",
  noNodes: "No server nodes have been added yet.",
  addFirstNode: "Add First Node",
  repairSuccess: "Saved data was checked and repaired. Active issues: ",
  repairFailed: "Data repair could not be completed.",
  nodeHealthy: "Node connection is healthy.",
  checkFailed: "Connection check failed.",
  nodeDeleted: "Node was deleted.",
  coreDeleted: "Core was deleted.",
  coreSaved: "Core configuration was saved.",
  coreCreated: "Core configuration was created.",
  nodeSaved: "Node was saved.",
});

function escapeHtml(v) {
  return String(v ?? "").replace(
    /[&<>'"]/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[
        c
      ],
  );
}

function deepCopy(v) {
  return JSON.parse(JSON.stringify(v ?? {}));
}
function isValidNodeId(id) {
  return /^node_[A-Za-z0-9_-]{6,96}$/.test(String(id || "").trim());
}
function isValidCoreId(id) {
  return /^core_[A-Za-z0-9_-]{6,96}$/.test(String(id || "").trim());
}
function nodeById(id) {
  if (!isValidNodeId(id)) return null;
  return state.nodes.find((n) => String(n.id) === String(id)) || null;
}
function coreById(id) {
  if (!isValidCoreId(id)) return null;
  return state.cores.find((c) => String(c.id) === String(id)) || null;
}
function warnInvalidIdentifier(kind) {
  showToast(
    kind === "core" ? UI_TEXT.invalidCore : UI_TEXT.invalidNode,
    "warning",
  );
}
function cleanDisplayName(value, fallback) {
  var text = String(value || fallback || "").trim();
  return text || "Unnamed";
}

function nodeDisplayName(node) {
  if (!node) return UI_TEXT.unknownNode;
  return cleanDisplayName(node.name, node.address || UI_TEXT.unknownNode);
}

function nodeName(id) {
  const n = nodeById(id);
  return n ? nodeDisplayName(n) : UI_TEXT.unknownNode;
}

function ensureAdvancedConfig(draft) {
  if (!draft) return { enabled: false, json_config: "" };
  if (!draft.advanced_config || typeof draft.advanced_config !== "object") {
    draft.advanced_config = { enabled: false, json_config: "" };
  }
  if (typeof draft.advanced_config.json_config !== "string") {
    draft.advanced_config.json_config = "";
  }
  draft.advanced_config.enabled = !!draft.advanced_config.enabled;
  return draft.advanced_config;
}

function timeAgo(iso) {
  if (!iso) return "Not yet";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "Unknown time";
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 5) return "just now";
  if (sec < 60) return sec + " seconds ago";
  const min = Math.floor(sec / 60);
  if (min < 60) return min + " minute" + (min === 1 ? "" : "s") + " ago";
  const hr = Math.floor(min / 60);
  if (hr < 24) return hr + " hour" + (hr === 1 ? "" : "s") + " ago";
  const day = Math.floor(hr / 24);
  if (day < 30) return day + " day" + (day === 1 ? "" : "s") + " ago";
  const mo = Math.floor(day / 30);
  if (mo < 12) return mo + " month" + (mo === 1 ? "" : "s") + " ago";
  const yr = Math.floor(mo / 12);
  return yr + " year" + (yr === 1 ? "" : "s") + " ago";
}

function formatApiError(data, fallback) {
  fallback = fallback || "Request could not be completed.";
  if (!data || typeof data !== "object") return fallback;
  if (typeof data.detail === "string") return data.detail;
  if (data.detail && typeof data.detail === "object" && !Array.isArray(data.detail)) {
    return data.detail.message || data.detail.error || fallback;
  }
  if (Array.isArray(data.detail) && data.detail.length) {
    var first = data.detail[0];
    var loc = Array.isArray(first.loc) ? first.loc.slice(1).join(" > ") : "";
    return loc ? loc + ": " + (first.msg || "invalid") : first.msg || fallback;
  }
  return data.message || data.error || fallback;
}

// ============================================================
// 2. STATE
// ============================================================

const state = {
  user: null,
  nodes: [],
  cores: [],
  inboundCatalog: [],
  stats: null,
  page: "dashboard",
  editingNode: null,
  editingCore: null,
  editorDraft: null,
  lastFormCheck: null,
  currentCoreTab: "inbounds",
  logSources: [],
  currentLogSource: "panel",
  logAutoRefreshTimer: null,
  logRefreshIntervalSeconds: 10,
  logsLoading: false,
  rawLogLines: [],
  endpointOpen: {},
  editorCardOpen: {},
};

function editorCardKey(type, index, extra) {
  return String(type || "card") + ":" + String(index) + (extra ? ":" + String(extra) : "");
}

function isEditorCardOpen(type, index, extra) {
  return state.editorCardOpen[editorCardKey(type, index, extra)] !== false;
}

function editorCollapseButton(type, index, isOpen, label, extra) {
  return (
    '<button type="button" class="editor-collapse-btn" data-action="toggle-editor-card" data-card-type="' +
    escapeHtml(type) +
    '" data-card-index="' +
    escapeHtml(String(index)) +
    '" data-card-extra="' +
    escapeHtml(extra || "") +
    '" aria-label="' +
    escapeHtml(label || "Toggle card") +
    '" title="' +
    escapeHtml(label || "Toggle card") +
    '"><i class="fa-solid ' +
    (isOpen ? "fa-chevron-down" : "fa-chevron-right") +
    '" aria-hidden="true"></i></button>'
  );
}

function bindEditorCardToggles(root) {
  if (!root) return;
  root.querySelectorAll('[data-action="toggle-editor-card"]').forEach(function (btn) {
    btn.addEventListener("click", function () {
      var type = btn.dataset.cardType || "card";
      var idx = btn.dataset.cardIndex || "0";
      var extra = btn.dataset.cardExtra || "";
      var key = editorCardKey(type, idx, extra);
      state.editorCardOpen[key] = state.editorCardOpen[key] === false;
      var card = btn.closest(".editor-card");
      var isOpen = state.editorCardOpen[key] !== false;
      if (card) {
        card.classList.toggle("is-collapsed", !isOpen);
        card.classList.toggle("is-open", isOpen);
      }
      var icon = btn.querySelector("i");
      if (icon) {
        icon.classList.toggle("fa-chevron-down", isOpen);
        icon.classList.toggle("fa-chevron-right", !isOpen);
      }
    });
  });
}


// ============================================================
// 3. API HELPER
// ============================================================

async function api(path, options) {
  options = options || {};
  var res = await fetch(
    path,
    Object.assign(
      {
        credentials: "same-origin",
        headers: Object.assign(
          { "Content-Type": "application/json" },
          options.headers || {},
        ),
      },
      options,
    ),
  );
  var data = await res.json().catch(function () {
    return {};
  });
  if (!res.ok) throw new Error(formatApiError(data));
  return data;
}

// ============================================================
// 4. TOAST SYSTEM
// ============================================================

function showToast(message, type, duration) {
  type = type || "info";
  duration = duration === undefined ? 4500 : duration;

  var icons = {
    success:
      '<i class="fa-solid fa-check" aria-hidden="true"></i>',
    error:
      '<i class="fa-solid fa-circle-exclamation" aria-hidden="true"></i>',
    warning:
      '<i class="fa-solid fa-triangle-exclamation" aria-hidden="true"></i>',
    info: '<i class="fa-solid fa-circle-info" aria-hidden="true"></i>',
  };

  var container = $("#toastContainer");
  if (!container) return;

  var toast = document.createElement("div");
  toast.className = "toast toast--" + type;
  toast.innerHTML =
    '<span class="toast-icon">' +
    (icons[type] || icons.info) +
    "</span>" +
    '<span class="toast-message">' +
    escapeHtml(message) +
    "</span>" +
    '<button class="toast-close" aria-label="Dismiss">&times;</button>';

  container.appendChild(toast);

  requestAnimationFrame(function () {
    requestAnimationFrame(function () {
      toast.classList.add("toast--visible");
    });
  });

  function remove() {
    toast.classList.remove("toast--visible");
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 350);
  }

  toast.querySelector(".toast-close").addEventListener("click", remove);
  if (duration > 0) setTimeout(remove, duration);
}

// ============================================================
// 5. CONFIRM DIALOG
// ============================================================

function showConfirm(message, title, confirmText, type) {
  title = title || "Confirm Action";
  confirmText = confirmText || "Delete";
  type = type || "danger";

  return new Promise(function (resolve) {
    var dialog = $("#confirmDialog");
    var titleEl = $("#confirmTitle");
    var messageEl = $("#confirmMessage");
    var okBtn = $("#confirmOk");
    var cancelBtn = $("#confirmCancel");

    if (!dialog) {
      resolve(false);
      return;
    }

    if (titleEl) titleEl.textContent = title;
    if (messageEl) messageEl.textContent = message;
    if (okBtn) {
      okBtn.textContent = confirmText;
      okBtn.className = "btn btn-" + type;
    }

    dialog.classList.remove("hidden");

    var handled = false;
    function done(result) {
      if (handled) return;
      handled = true;
      dialog.classList.add("hidden");
      if (okBtn) okBtn.removeEventListener("click", onOk);
      if (cancelBtn) cancelBtn.removeEventListener("click", onCancel);
      resolve(result);
    }

    function onOk() {
      done(true);
    }
    function onCancel() {
      done(false);
    }

    if (okBtn) okBtn.addEventListener("click", onOk);
    if (cancelBtn) cancelBtn.addEventListener("click", onCancel);
  });
}

// ============================================================
// 6. AUTH
// ============================================================

async function checkSession() {
  try {
    var data = await api("/api/auth/me");
    if (data.ok) showApp(data.username);
    else showLogin();
  } catch (_) {
    showLogin();
  }
}

async function handleLoginSubmit(e) {
  e.preventDefault();
  var form = e.target;
  var unameEl = $("#usernameInput");
  var pwdEl = $("#passwordInput");
  var username = unameEl ? unameEl.value.trim() : "";
  var password = pwdEl ? pwdEl.value : "";
  var submitBtn = form.querySelector('[type="submit"]');
  var btnText = $("#loginBtnText");
  var errorEl = $("#loginMessage");

  if (errorEl) errorEl.textContent = "";
  var origText = btnText ? btnText.textContent : "Sign In";
  if (submitBtn) submitBtn.disabled = true;
  if (btnText) btnText.textContent = "Signing in…";

  try {
    var data = await api("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username: username, password: password }),
    });
    if (data.ok) {
      showApp(data.username);
    } else {
      var msg = "Login failed. Please try again.";
      if (errorEl) errorEl.textContent = msg;
      showToast(msg, "error");
    }
  } catch (err) {
    var msg2 = err.message || "Login failed.";
    if (errorEl) errorEl.textContent = msg2;
    showToast(msg2, "error");
  } finally {
    if (submitBtn) submitBtn.disabled = false;
    if (btnText) btnText.textContent = origText;
  }
}

async function handleLogout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (_) {}
  state.user = null;
  state.nodes = [];
  state.cores = [];
  state.stats = null;
  showLogin();
}

function togglePasswordVisibility() {
  var input = $("#passwordInput");
  var btn = $("#togglePassword");
  if (!input) return;
  input.type = input.type === "password" ? "text" : "password";
  if (btn)
    btn.setAttribute(
      "aria-label",
      input.type === "password" ? "Show password" : "Hide password",
    );
}

// ============================================================
// 7. NAVIGATION
// ============================================================

function showApp(username) {
  state.user = username;
  var nameEl = $("#adminName");
  if (nameEl) nameEl.textContent = username;
  var loginView = $("#loginView");
  var appView = $("#appView");
  if (loginView) loginView.classList.add("hidden");
  if (appView) appView.classList.remove("hidden");
  refreshAll();
}

function showLogin() {
  var appView = $("#appView");
  var loginView = $("#loginView");
  if (appView) appView.classList.add("hidden");
  if (loginView) loginView.classList.remove("hidden");
}

function switchPage(page) {
  if (state.page === "logs" && page !== "logs") {
    stopLogAutoRefresh(true);
  }

  state.page = page;

  $$(".nav-item[data-page]").forEach(function (btn) {
    btn.classList.toggle("active", btn.dataset.page === page);
  });

  $$(".page").forEach(function (s) {
    s.classList.remove("active");
  });
  var editorPage = $("#coreEditorPage");
  if (editorPage) editorPage.classList.remove("active");

  var target = $("#" + page + "Page");
  if (target) target.classList.add("active");

  if (page === "logs")
    loadLogSources().then(function () {
      loadLogs();
    });
  else if (page === "dashboard") loadStats();
  else if (page === "nodes") renderNodes();
  else if (page === "cores") renderCores();
}

function openCoreEditorPage(core) {
  if (!core || !isValidCoreId(core.id)) { warnInvalidIdentifier("core"); return; }
  state.editingCore = core;
  state.editorDraft = deepCopy(core);

  if (!Array.isArray(state.editorDraft.inbounds))
    state.editorDraft.inbounds = [];
  if (!Array.isArray(state.editorDraft.balancers))
    state.editorDraft.balancers = [];
  if (!Array.isArray(state.editorDraft.dependencies))
    state.editorDraft.dependencies = [];
  ensureAdvancedConfig(state.editorDraft);

  $$(".nav-item[data-page]").forEach(function (btn) {
    btn.classList.remove("active");
  });
  $$(".page").forEach(function (s) {
    s.classList.remove("active");
  });

  state.page = "coreEditor";
  var ep = $("#coreEditorPage");
  if (ep) ep.classList.add("active");

  var bc = $("#editorBreadcrumbName");
  if (bc) bc.textContent = core.name || "Core Editor";

  bindCoreEditorHeader();
  switchCoreTab("inbounds");
  renderCoreEditor();
}

// ============================================================
// 8. DATA LOADING
// ============================================================

async function refreshAll() {
  await Promise.all([loadNodes(), loadCores()]);
  if (state.page === "dashboard") await loadStats();
}

async function repairPanelData() {
  var confirmed = await showConfirm(
    "Repair invalid nodes and cores? Invalid records will be removed and cores linked to missing nodes will be disabled.",
    "Repair Data",
    "Repair",
    "warning",
  );
  if (!confirmed) return;
  try {
    var data = await api("/api/panel/repair", { method: "POST" });
    var summary = data.integrity && data.integrity.summary ? data.integrity.summary : {};
    showToast(
      UI_TEXT.repairSuccess + String(summary.problems_total || 0),
      summary.problems_total ? "warning" : "success",
    );
    await refreshAll();
  } catch (err) {
    showToast(err.message || UI_TEXT.repairFailed, "error");
  }
}

async function loadStats() {
  try {
    var data = await api("/api/panel/stats");
    if (data.ok) {
      state.stats = data;
      renderDashboard();
    }
  } catch (err) {
    console.error("loadStats:", err);
  }
}

async function loadNodes() {
  try {
    var data = await api("/api/nodes");
    if (data.ok) {
      state.nodes = (data.nodes || []).filter(function (node) { return isValidNodeId(node && node.id); });
      renderNodes();
      updateNodesBadge();
    }
  } catch (err) {
    console.error("loadNodes:", err);
  }
}

async function loadCores() {
  try {
    var data = await api("/api/cores");
    if (data.ok) {
      state.cores = (data.cores || []).filter(function (core) { return isValidCoreId(core && core.id); });
      state.inboundCatalog = data.inbound_catalog || [];
      renderCores();
      updateCoresBadge();
    }
  } catch (err) {
    console.error("loadCores:", err);
  }
}

function updateNodesBadge() {
  var badge = $("#nodesBadge");
  if (!badge) return;
  var count = state.nodes.filter(function (n) {
    return n.enabled && n.status === "error";
  }).length;
  badge.textContent = count;
  badge.classList.toggle("hidden", count === 0);
}

function updateCoresBadge() {
  var badge = $("#coresBadge");
  if (!badge) return;
  var count = state.cores.filter(function (c) {
    return !c.enabled;
  }).length;
  badge.textContent = count;
  badge.classList.toggle("hidden", count === 0);
}

// ============================================================
// 9. STATUS HELPERS
// ============================================================

function statusFor(item) {
  if (!item) return "pending";
  if (!item.enabled) return "disabled";
  var s = item.status;
  if (
    s === "running" ||
    s === "error" ||
    s === "pending" ||
    s === "ready" ||
    s === "applied" ||
    s === "draft"
  )
    return s;
  return "pending";
}

function statusLabel(status) {
  var labels = {
    running: "Running",
    error: "Error",
    pending: "Pending",
    ready: "Ready",
    applied: "Applied",
    draft: "Draft",
    disabled: "Disabled",
  };
  return labels[status] || "Unknown";
}

function statusDotClass(status) {
  if (status === "running") return "running";
  if (status === "error") return "error";
  if (status === "disabled") return "disabled";
  return "pending";
}

// ============================================================
// 10. DASHBOARD
// ============================================================

function renderDashboard() {
  var stats = state.stats;
  if (!stats) return;

  function set(id, val) {
    var el = $(id);
    if (el) el.textContent = val !== null && val !== undefined ? val : "\u2014";
  }

  var nodes = stats.nodes || {};
  var cores = stats.cores || {};
  var inbounds = stats.inbounds || {};
  var balancers = stats.balancers || {};

  set("#statTotalNodes", nodes.total != null ? nodes.total : 0);
  set("#statRunningNodes", nodes.running != null ? nodes.running : 0);
  set("#statErrorNodes", nodes.error != null ? nodes.error : 0);
  set("#statTotalCores", cores.total != null ? cores.total : 0);
  set("#statEnabledCores", cores.enabled != null ? cores.enabled : 0);
  set("#statTotalInbounds", inbounds.total != null ? inbounds.total : 0);
  set("#statEnabledInbounds", inbounds.enabled != null ? inbounds.enabled : 0);
  set("#statTotalBalancers", balancers.total != null ? balancers.total : 0);

  var errWrap = $("#statErrorNodes");
  if (errWrap) errWrap.classList.toggle("hidden", !(nodes.error > 0));

  var nodeList = $("#dashboardNodeList");
  if (!nodeList) return;

  if (!state.nodes.length) {
    nodeList.innerHTML =
      '<div class="dashboard-empty">' +
      "<p>No server nodes have been added yet.</p>" +
      '<button class="btn btn-primary btn-sm" id="dashEmptyAddNode">Add First Node</button>' +
      "</div>";
    var addBtn = $("#dashEmptyAddNode");
    if (addBtn)
      addBtn.addEventListener("click", function () {
        openNodeModal();
      });
    return;
  }

  nodeList.innerHTML = state.nodes
    .map(function (node) {
      var st = statusFor(node);
      var dot = statusDotClass(st);
      var addr =
        escapeHtml(node.address || "") +
        ":" +
        escapeHtml(String(node.api_port || ""));
      var tt = node.last_error
        ? ' title="' + escapeHtml(node.last_error) + '"'
        : "";
      return (
        '<div class="dashboard-node-item"' +
        tt +
        ">" +
        '<span class="status-dot ' +
        dot +
        '"></span>' +
        '<div class="dashboard-node-info">' +
        '<span class="dashboard-node-name">' +
        escapeHtml(node.name || node.address) +
        "</span>" +
        '<span class="dashboard-node-addr">' +
        addr +
        "</span>" +
        "</div>" +
        '<div class="dashboard-node-actions">' +
        '<button class="btn btn-xs btn-ghost" data-action="check" data-id="' +
        escapeHtml(String(node.id || "")) +
        '" title="Check node">' +
        '<i class="fa-solid fa-rotate-right" aria-hidden="true"></i>' +
        "</button>" +
        '<button class="btn btn-xs btn-ghost" data-action="edit" data-id="' +
        escapeHtml(String(node.id || "")) +
        '" title="Edit node">' +
        '<i class="fa-solid fa-pen-to-square" aria-hidden="true"></i>' +
        "</button>" +
        "</div>" +
        "</div>"
      );
    })
    .join("");

  nodeList.querySelectorAll("[data-action]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var id = btn.dataset.id;
      if (!isValidNodeId(id)) { warnInvalidIdentifier("node"); return; }
      if (btn.dataset.action === "edit") openNodeModal(nodeById(id));
      if (btn.dataset.action === "check") checkSavedNode(id, btn);
    });
  });
}

// ============================================================
// 11. NODES PAGE
// ============================================================

function renderNodes() {
  var tbody = $("#nodesTableBody");
  var empty = $("#nodesEmpty");
  var tableWrap = $("#nodesTableWrap");
  if (!tbody) return;

  if (!state.nodes.length) {
    if (empty) empty.classList.remove("hidden");
    if (tableWrap) tableWrap.classList.add("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  if (tableWrap) tableWrap.classList.remove("hidden");

  tbody.innerHTML = state.nodes
    .map(function (node) {
      var st = statusFor(node);
      var titleAttr = node.last_error
        ? ' title="' + escapeHtml(node.last_error) + '"'
        : "";
      var checkedAt = node.last_checked_at
        ? timeAgo(node.last_checked_at)
        : "Not yet";
      return (
        "<tr" +
        titleAttr +
        ">" +
        '<td><span class="badge badge-' +
        escapeHtml(st) +
        '">' +
        escapeHtml(statusLabel(st)) +
        "</span></td>" +
        "<td>" +
        escapeHtml(node.name || "\u2014") +
        "</td>" +
        "<td>" +
        escapeHtml(node.address || "\u2014") +
        "</td>" +
        "<td>" +
        escapeHtml(String(node.api_port || "\u2014")) +
        "</td>" +
        "<td>" +
        escapeHtml(node.connection_type || "\u2014") +
        "</td>" +
        "<td>" +
        (node.certificate ? "Yes" : "No") +
        "</td>" +
        '<td><span class="badge ' +
        (node.enabled ? "badge-running" : "badge-disabled") +
        '">' +
        (node.enabled ? "Enabled" : "Disabled") +
        "</span></td>" +
        "<td>" +
        escapeHtml(checkedAt) +
        "</td>" +
        '<td class="actions-cell">' +
        '<button class="btn btn-xs btn-ghost" data-node-action="check" data-id="' +
        escapeHtml(String(node.id || "")) +
        '" title="Check">' +
        '<i class="fa-solid fa-rotate-right" aria-hidden="true"></i>' +
        "</button>" +
        '<button class="btn btn-xs btn-secondary" data-node-action="edit"   data-id="' +
        escapeHtml(String(node.id || "")) +
        '">Edit</button>' +
        '<button class="btn btn-xs btn-danger"    data-node-action="delete" data-id="' +
        escapeHtml(String(node.id || "")) +
        '">Delete</button>' +
        "</td>" +
        "</tr>"
      );
    })
    .join("");

  tbody.querySelectorAll("[data-node-action]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var id = btn.dataset.id;
      var action = btn.dataset.nodeAction;
      if (!isValidNodeId(id)) { warnInvalidIdentifier("node"); return; }
      if (action === "check") checkSavedNode(id, btn);
      if (action === "edit") openNodeModal(nodeById(id));
      if (action === "delete") deleteNode(id);
    });
  });
}

function openNodeModal(node) {
  node = node || null;
  state.editingNode = node;
  state.lastFormCheck = null;
  resetNodeForm();

  var modal = $("#nodeModal");
  var titleEl = $("#nodeModalTitle");
  var deleteBtn = $("#deleteNodeButton");

  if (node) {
    if (titleEl) titleEl.textContent = "Edit Node";
    if (deleteBtn) deleteBtn.classList.remove("hidden");

    function setVal(sel, val) {
      var el = $(sel);
      if (el) el.value = val != null ? val : "";
    }
    setVal("#nodeName", node.name);
    setVal("#nodeAddress", node.address);
    setVal("#apiPort", node.api_port);
    setVal("#connectionType", "grpc");
    setVal("#apiKey", node.api_key);

    var tlsEl = null; // TLS is managed via certificate field
    var enabledEl = $("#nodeEnabled");
    if (tlsEl) tlsEl.checked = !!node.tls;
    if (enabledEl) enabledEl.checked = !!node.enabled;
  } else {
    if (titleEl) titleEl.textContent = "Add Node";
    if (deleteBtn) deleteBtn.classList.add("hidden");
  }

  updateStatusPreview();
  if (modal) modal.classList.remove("hidden");
}

function closeNodeModal() {
  var modal = $("#nodeModal");
  if (modal) modal.classList.add("hidden");
  state.editingNode = null;
  state.lastFormCheck = null;
}

function resetNodeForm() {
  var form = $("#nodeForm");
  if (form) form.reset();
  setStatusPreview("pending", "Not checked");
}

function nodePayload() {
  function get(sel) {
    var el = $(sel);
    return el ? el.value.trim() : "";
  }
  function getChecked(sel) {
    var el = $(sel);
    return el ? el.checked : false;
  }
  return {
    name: get("#nodeName"),
    address: get("#nodeAddress"),
    api_port: parseInt(get("#apiPort"), 10) || 62051,
    connection_type: "grpc",
    api_key: get("#apiKey"),
    enabled: getChecked("#nodeEnabled"),
  };
}

function setStatusPreview(status, message) {
  message = message || "";
  var dot = $("#nodeStatusDot");
  var text = $("#nodeStatusText");
  if (dot) {
    dot.className = "status-dot " + statusDotClass(status);
  }
  if (text) {
    text.textContent = message || statusLabel(status);
  }
}

function updateStatusPreview() {
  var enabledEl = $("#nodeEnabled");
  if (enabledEl && !enabledEl.checked) {
    setStatusPreview("disabled", "Disabled");
    return;
  }
  if (state.lastFormCheck) {
    setStatusPreview(
      state.lastFormCheck.status,
      state.lastFormCheck.message || statusLabel(state.lastFormCheck.status),
    );
  } else {
    setStatusPreview("pending", "Not checked");
  }
}

async function saveNode(e) {
  e.preventDefault();
  var payload = nodePayload();
  var submitBtn = $('#nodeForm [type="submit"]') || $("#nodeForm button");
  var origText = submitBtn ? submitBtn.textContent : "";
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Saving\u2026";
  }

  try {
    if (state.editingNode) {
      if (!isValidNodeId(state.editingNode.id)) { warnInvalidIdentifier("node"); await refreshAll(); return; }
      await api("/api/nodes/" + encodeURIComponent(state.editingNode.id), {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      showToast("Node updated successfully.", "success");
    } else {
      await api("/api/nodes", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      showToast("Node created successfully.", "success");
    }
    closeNodeModal();
    await refreshAll();
  } catch (err) {
    showToast(err.message || "Failed to save node.", "error");
  } finally {
    if (submitBtn) submitBtn.disabled = false;
    if (btnText) btnText.textContent = origText;
  }
}

async function deleteNode(id) {
  if (!isValidNodeId(id)) { warnInvalidIdentifier("node"); await refreshAll(); return; }
  var node = nodeById(id);
  var name = node ? node.name || node.address : "Node #" + id;
  var confirmed = await showConfirm(
    'Are you sure you want to delete "' + name + '"? This cannot be undone.',
    "Delete Node",
    "Delete",
    "danger",
  );
  if (!confirmed) return;

  try {
    await api("/api/nodes/" + encodeURIComponent(id), { method: "DELETE" });
    showToast("Node deleted.", "success");
    closeNodeModal();
    await refreshAll();
  } catch (err) {
    if ((err.message || "").toLowerCase().includes("node not found")) {
      showToast("Node was already removed. The list was refreshed.", "warning");
      closeNodeModal();
      await refreshAll();
      return;
    }
    showToast(err.message || "Failed to delete node.", "error");
  }
}

async function checkSavedNode(id, button) {
  if (!isValidNodeId(id)) { warnInvalidIdentifier("node"); await refreshAll(); return; }
  var origHTML = button ? button.innerHTML : "";
  if (button) button.disabled = true;

  try {
    var data = await api("/api/nodes/" + encodeURIComponent(id) + "/check", { method: "POST" });
    var status = data.status || "unknown";
    var msg = data.message || statusLabel(status);
    showToast(
      "Node check: " + msg,
      status === "running" ? "success" : status === "error" ? "error" : "info",
    );
    await refreshAll();
  } catch (err) {
    showToast(err.message || "Node check failed.", "error");
  } finally {
    if (button) {
      button.disabled = false;
      button.innerHTML = origHTML;
    }
  }
}

async function checkFormNode() {
  var checkBtn = $("#checkNodeStatus");
  var origText = checkBtn ? checkBtn.textContent : "";
  if (checkBtn) {
    checkBtn.disabled = true;
    checkBtn.textContent = "Checking…";
  }

  try {
    if (state.editingNode) {
      if (!isValidNodeId(state.editingNode.id)) { warnInvalidIdentifier("node"); await refreshAll(); return; }
      var payload = nodePayload();
      await api("/api/nodes/" + encodeURIComponent(state.editingNode.id), {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      var data = await api("/api/nodes/" + encodeURIComponent(state.editingNode.id) + "/check", {
        method: "POST",
      });
      state.lastFormCheck = {
        status: data.status || "unknown",
        message: data.message,
      };
      updateStatusPreview();
      showToast(
        "Node check: " +
          (data.message || statusLabel(state.lastFormCheck.status)),
        data.status === "running"
          ? "success"
          : data.status === "error"
            ? "error"
            : "info",
      );
      await refreshAll();
    } else {
      var payload2 = nodePayload();
      var data2 = await api("/api/nodes/check", {
        method: "POST",
        body: JSON.stringify(payload2),
      });
      state.lastFormCheck = {
        status: data2.status || "unknown",
        message: data2.message,
      };
      updateStatusPreview();
      showToast(
        "Node check: " +
          (data2.message || statusLabel(state.lastFormCheck.status)),
        data2.status === "running"
          ? "success"
          : data2.status === "error"
            ? "error"
            : "info",
      );
    }
  } catch (err) {
    state.lastFormCheck = { status: "error", message: err.message };
    updateStatusPreview();
    showToast(err.message || UI_TEXT.checkFailed, "error");
  } finally {
    if (checkBtn) {
      checkBtn.disabled = false;
      checkBtn.textContent = origText;
    }
  }
}

function fillNodeSelect(select, value) {
  value = value || "";
  if (!select) return;
  select.innerHTML =
    '<option value="">— Select Node —</option>' +
    state.nodes
      .filter(function (n) { return isValidNodeId(n && n.id); })
      .map(function (n) {
        var v = String(n.id);
        var sel = v === String(value) ? " selected" : "";
        var label = escapeHtml(nodeDisplayName(n));
        return '<option value="' + v + '"' + sel + ">" + label + "</option>";
      })
      .join("");
}

// ============================================================
// 12. CORES PAGE
// ============================================================

function renderCores() {
  var grid = $("#coresGrid");
  var empty = $("#coresEmpty");
  if (!grid) return;

  if (!state.cores.length) {
    if (empty) empty.classList.remove("hidden");
    grid.classList.add("hidden");
    return;
  }
  if (empty) empty.classList.add("hidden");
  grid.classList.remove("hidden");

  grid.innerHTML = state.cores
    .map(function (core) {
      var st = statusFor(core);
      var inCnt = Array.isArray(core.inbounds) ? core.inbounds.length : 0;
      var enabledInbounds = Array.isArray(core.inbounds)
        ? core.inbounds.filter(function (ib) { return ib.enabled !== false; }).length
        : 0;
      var blCnt = Array.isArray(core.balancers) ? core.balancers.length : 0;
      var dpCnt = Array.isArray(core.dependencies) ? core.dependencies.length : 0;
      var upd = core.updated_at ? timeAgo(core.updated_at) : "unknown";
      var applied = core.last_applied_at ? timeAgo(core.last_applied_at) : UI_TEXT.notApplied;
      var coreIdOk = isValidCoreId(core.id);
      var node = nodeById(core.node_id);
      var nodeMissing = !node;
      var nName = nodeMissing ? UI_TEXT.missingNode : nodeName(core.node_id);
      var nodeStatus = nodeMissing ? "error" : statusFor(node);
      var healthClass = nodeStatus === "running" ? "ok" : nodeStatus === "error" ? "bad" : "warn";
      var actionDisabled = !coreIdOk || nodeMissing;
      var disabledAttr = actionDisabled ? ' disabled title="This core has invalid or missing linked data. Run Repair Data."' : "";
      return (
        '<article class="core-card core-card-v2" data-id="' + escapeHtml(String(core.id)) + '">' +
          '<div class="core-card-topline">' +
            '<span class="badge badge-' + escapeHtml(st) + '">' + escapeHtml(statusLabel(st)) + '</span>' +
            '<span class="core-health core-health-' + healthClass + '">' +
              '<span class="status-dot-mini"></span>' + escapeHtml(nodeMissing ? "Broken Link" : nodeStatus === "running" ? "Node online" : nodeStatus === "error" ? "Node issue" : "Pending node") +
            '</span>' +
          '</div>' +
          '<div class="core-card-main">' +
            '<h3 class="core-card-name">' + escapeHtml(core.name || "Unnamed Core") + '</h3>' +
            '<div class="core-card-node-line">' +
              '<span class="tiny-icon"><i class="fa-solid fa-desktop" aria-hidden="true"></i></span>' +
              '<span>' + escapeHtml(nName) + '</span>' +
            '</div>' +
          '</div>' +
          '<div class="core-metrics-grid">' +
            '<div class="core-metric"><strong>' + inCnt + '</strong><span>Inbounds</span><small>' + enabledInbounds + ' enabled</small></div>' +
            '<div class="core-metric"><strong>' + blCnt + '</strong><span>Balancers</span><small>routing groups</small></div>' +
            '<div class="core-metric"><strong>' + dpCnt + '</strong><span>Deps</span><small>apply order</small></div>' +
          '</div>' +
          '<div class="core-card-footer core-card-footer-v2">' +
            '<div class="core-time-stack">' +
              '<span>Updated ' + escapeHtml(upd) + '</span>' +
              '<span>Applied: ' + escapeHtml(applied) + '</span>' +
              (core.last_error ? '<span class="core-error-inline">' + escapeHtml(core.last_error) + '</span>' : '') +
            '</div>' +
            '<div class="core-card-actions">' +
              '<button class="btn btn-sm btn-ghost" data-core-action="open" data-id="' + escapeHtml(String(core.id || "")) + '"' + (coreIdOk ? "" : disabledAttr) + '>Open</button>' +
              '<button class="btn btn-sm btn-primary" data-core-action="apply" data-id="' + escapeHtml(String(core.id || "")) + '"' + disabledAttr + '>Apply</button>' +
              '<button class="btn btn-sm btn-danger" data-core-action="delete" data-id="' + escapeHtml(String(core.id || "")) + '"' + (coreIdOk ? "" : disabledAttr) + '>Delete</button>' +
            '</div>' +
          '</div>' +
        '</article>'
      );
    })
    .join("");

  grid.querySelectorAll("[data-core-action]").forEach(function (btn) {
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var id = btn.dataset.id;
      if (!isValidCoreId(id)) { warnInvalidIdentifier("core"); return; }
      if (btn.disabled) { warnInvalidIdentifier("core"); return; }
      if (btn.dataset.coreAction === "open") openCoreEditorPage(coreById(id));
      if (btn.dataset.coreAction === "apply") applyCore(id, btn);
      if (btn.dataset.coreAction === "delete") deleteCore(id);
    });
  });

  grid.querySelectorAll(".core-card").forEach(function (card) {
    card.addEventListener("dblclick", function () {
      var id = card.dataset.id;
      if (!isValidCoreId(id)) { warnInvalidIdentifier("core"); return; }
      openCoreEditorPage(coreById(id));
    });
  });
}

async function applyCore(id, button) {
  if (!isValidCoreId(id)) { warnInvalidIdentifier("core"); await refreshAll(); return; }
  var core = coreById(id);
  if (core && !nodeById(core.node_id)) { warnInvalidIdentifier("core"); await refreshAll(); return; }
  var orig = button ? button.textContent : "";
  if (button) {
    button.disabled = true;
    button.textContent = "Applying…";
  }
  try {
    var data = await api("/api/cores/" + encodeURIComponent(id) + "/apply", { method: "POST" });
    showToast(data.message || "Core applied to node.", "success");
    await refreshAll();
  } catch (err) {
    showToast(err.message || "Failed to apply core.", "error");
    await refreshAll();
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = orig;
    }
  }
}

async function openCoreCreateModal() {
  if (!state.nodes.length) {
    await loadNodes();
  }

  if (!state.nodes.length) {
    showToast("No nodes available. Please add a node first.", "warning");
    return;
  }

  var select = $("#createCoreNode");
  if (select) fillNodeSelect(select, "");

  var modal = $("#coreCreateModal");
  if (modal) modal.classList.remove("hidden");
}

function closeCoreCreateModal() {
  var modal = $("#coreCreateModal");
  if (modal) modal.classList.add("hidden");
  var form = $("#coreCreateForm");
  if (form) form.reset();
}

async function createCore(e) {
  e.preventDefault();
  var nameEl = $("#createCoreName");
  var nodeEl = $("#createCoreNode");
  var submitBtn = e.target.querySelector('[type="submit"]');

  var name = nameEl ? nameEl.value.trim() : "";
  var node_id = nodeEl ? nodeEl.value : "";

  if (!name) {
    showToast("Core name is required.", "warning");
    return;
  }
  if (!node_id || !isValidNodeId(node_id)) {
    showToast("Please select a valid node.", "warning");
    return;
  }

  var origText = submitBtn ? submitBtn.textContent : "";
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "Creating\u2026";
  }

  try {
    var data = await api("/api/cores", {
      method: "POST",
      body: JSON.stringify({ name: name, node_id: node_id, enabled: true }),
    });
    if (data.ok) {
      closeCoreCreateModal();
      showToast("Core created.", "success");
      await refreshAll();
      openCoreEditorPage(data.core);
    }
  } catch (err) {
    showToast(err.message || "Failed to create core.", "error");
  } finally {
    if (submitBtn) submitBtn.disabled = false;
    if (btnText) btnText.textContent = origText;
  }
}

async function deleteCore(id) {
  if (!isValidCoreId(id)) { warnInvalidIdentifier("core"); await refreshAll(); return; }
  var core = coreById(id);
  var name = core ? core.name : "Core #" + id;
  var confirmed = await showConfirm(
    'Are you sure you want to delete "' + name + '"? This cannot be undone.',
    "Delete Core",
    "Delete",
    "danger",
  );
  if (!confirmed) return;

  try {
    await api("/api/cores/" + encodeURIComponent(id), { method: "DELETE" });
    showToast("Core deleted.", "success");
    if (state.editingCore && state.editingCore.id === id) switchPage("cores");
    await refreshAll();
  } catch (err) {
    if ((err.message || "").toLowerCase().includes("core not found")) {
      showToast("Core was already removed. The list was refreshed.", "warning");
      await refreshAll();
      return;
    }
    showToast(err.message || "Failed to delete core.", "error");
  }
}

// ============================================================
// 13. CORE EDITOR
// ============================================================

function bindCoreEditorHeader() {
  var draft = state.editorDraft;
  if (!draft) return;
  var nameEl = $("#editorCoreName");
  var nodeEl = $("#editorCoreNode");
  var enabledEl = $("#editorCoreEnabled");
  if (nameEl) nameEl.value = draft.name || "";
  if (nodeEl) fillNodeSelect(nodeEl, draft.node_id);
  if (enabledEl) enabledEl.checked = !!draft.enabled;
}

function syncEditorHeaderToDraft() {
  if (!state.editorDraft) return;
  var nameEl = $("#editorCoreName");
  var nodeEl = $("#editorCoreNode");
  var enabledEl = $("#editorCoreEnabled");
  if (nameEl) state.editorDraft.name = nameEl.value.trim();
  if (nodeEl) state.editorDraft.node_id = nodeEl.value || "";
  if (enabledEl) state.editorDraft.enabled = enabledEl.checked;
}

function switchCoreTab(tab) {
  tab = tab || "inbounds";
  state.currentCoreTab = tab;
  $$(".tab-btn").forEach(function (btn) {
    var key = btn.dataset.coreTab || btn.dataset.tab || "";
    var active = key === tab;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  $$(".tab-panel").forEach(function (panel) {
    var key = panel.dataset.coreTab || panel.dataset.tab || "";
    panel.classList.toggle("active", key === tab);
  });
  if (tab === "advanced") renderAdvancedEditor();
}

function renderCoreEditor() {
  renderInboundEditor();
  renderRoutingEditor();
  renderBalancerEditor();
  renderDependencyEditor();
  renderAdvancedEditor();
  updateTabBadges();
}

function updateTabBadges() {
  var draft = state.editorDraft;
  if (!draft) return;
  var ib = $("#inboundTabBadge");
  var bb = $("#balancerTabBadge");
  if (ib) ib.textContent = (draft.inbounds || []).length;
  if (bb) bb.textContent = (draft.balancers || []).length;
}

function defaultInbound() {
  return {
    name: "",
    bind_ip: "0.0.0.0",
    port_mode: "fixed",
    fixed_ports: [],
    random_count: 1,
    target_type: "static",
    target_host: "",
    target_port: "",
    target_balancer: "",
    certificate: "",
    enabled: true,
    notes: "",
  };
}

function defaultBalancer() {
  return {
    alias: "",
    strategy: "round_robin",
    endpoints: [],
    enabled: true,
    notes: "",
  };
}

function defaultEndpoint() {
  return {
    type: "static",
    host: "",
    port: 80,
    node_id: "",
    core_id: "",
    inbound_name: "",
    weight: 1,
    certificate: "",
    enabled: true,
    notes: "",
  };
}

function defaultDependency() {
  return { type: "core", ref_id: "", required: true, notes: "" };
}

function portsToText(ports) {
  return Array.isArray(ports) ? ports.join(",") : String(ports || "");
}

function parsePorts(text) {
  return String(text)
    .split(",")
    .map(function (p) {
      return parseInt(p.trim(), 10);
    })
    .filter(function (p) {
      return p >= 1 && p <= 65535;
    });
}

function currentBalancerAliases() {
  if (!state.editorDraft || !Array.isArray(state.editorDraft.balancers))
    return [];
  return state.editorDraft.balancers
    .map(function (b) {
      return b.alias;
    })
    .filter(Boolean);
}

// --- Inbound Editor ---

function renderInboundEditor() {
  var container = $("#inboundEditorList");
  if (!container || !state.editorDraft) return;
  var inbounds = state.editorDraft.inbounds || [];

  if (!inbounds.length) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = inbounds
    .map(function (ib, i) {
      var isFixed = ib.port_mode !== "random";
      var isOpen = isEditorCardOpen("inbound", i);
      var title = "Inbound " + (i + 1) + ": " + (ib.name || "Unnamed");
      return (
        '<div class="editor-card editor-card--collapsible' +
        (isOpen ? " is-open" : " is-collapsed") +
        '" data-in-index="' +
        i +
        '">' +
        '<div class="editor-card-header">' +
        '<div class="editor-card-heading">' +
        editorCollapseButton("inbound", i, isOpen, "Toggle inbound") +
        '<span class="editor-card-title"><span class="editor-card-title-main">' +
        escapeHtml(title) +
        '</span></span>' +
        '</div>' +
        '<button class="btn btn-xs btn-danger btn-remove-soft" data-in-index="' +
        i +
        '" data-action="remove-inbound" aria-label="Remove inbound">' +
        '<i class="fa-solid fa-trash-can" aria-hidden="true"></i><span>Remove</span></button>' +
        "</div>" +
        '<div class="editor-card-body">' +
        '<div class="form-row">' +
        '<div class="form-group"><label>Name</label>' +
        '<input type="text" class="form-input" data-in-index="' +
        i +
        '" data-field="name" value="' +
        escapeHtml(ib.name || "") +
        '"></div>' +
        '<div class="form-group"><label>Bind IP</label>' +
        '<input type="text" class="form-input" data-in-index="' +
        i +
        '" data-field="bind_ip" value="' +
        escapeHtml(ib.bind_ip || "0.0.0.0") +
        '"></div>' +
        "</div>" +
        '<div class="form-row">' +
        '<div class="form-group"><label>Port Mode</label>' +
        '<select class="form-input" data-in-index="' +
        i +
        '" data-field="port_mode">' +
        '<option value="fixed"' +
        (isFixed ? " selected" : "") +
        ">Fixed</option>" +
        '<option value="random"' +
        (!isFixed ? " selected" : "") +
        ">Random</option>" +
        "</select></div>" +
        '<div class="form-group"' +
        (!isFixed ? ' style="display:none"' : "") +
        ' data-in-fixed="' +
        i +
        '"><label>Fixed Ports (comma-separated)</label>' +
        '<input type="text" class="form-input" data-in-index="' +
        i +
        '" data-field="fixed_ports_text" value="' +
        escapeHtml(portsToText(ib.fixed_ports)) +
        '"></div>' +
        '<div class="form-group"' +
        (isFixed ? ' style="display:none"' : "") +
        ' data-in-random="' +
        i +
        '"><label>Random Count</label>' +
        '<input type="number" class="form-input" min="1" data-in-index="' +
        i +
        '" data-field="random_count" value="' +
        escapeHtml(String(ib.random_count || 1)) +
        '"></div>' +
        "</div>" +
        '<div class="form-row"><div class="form-group"><label>Certificate (optional)</label>' +
        '<textarea class="form-input" rows="2" data-in-index="' +
        i +
        '" data-field="certificate">' +
        escapeHtml(ib.certificate || "") +
        "</textarea></div>" +
        "</div>" +
        '<div class="form-row"><div class="form-group form-group--inline switch-field">' +
        '<label class="toggle-label toggle-label--inline toggle-label--state" for="inbEnabled_' +
        i +
        '">' +
        '<input type="checkbox" class="toggle-input" id="inbEnabled_' +
        i +
        '" data-in-index="' +
        i +
        '" data-field="enabled"' +
        (ib.enabled !== false ? " checked" : "") +
        ">" +
        '<span class="toggle-track" aria-hidden="true"><span class="toggle-thumb"></span></span>' +
        '<span class="toggle-text">Enabled</span></label>' +
        "</div></div>" +
        "</div>" +
        "</div>"
      );
    })
    .join("");

  bindEditorCardToggles(container);
  container.querySelectorAll("[data-in-index]").forEach(function (el) {
    if (el.tagName === "BUTTON" && el.dataset.action === "remove-inbound") {
      el.addEventListener("click", function () {
        state.editorDraft.inbounds.splice(parseInt(el.dataset.inIndex, 10), 1);
        renderCoreEditor();
      });
    } else if (el.tagName !== "BUTTON") {
      bindInboundField(el);
    }
  });
}

function bindInboundField(el) {
  var idx = parseInt(el.dataset.inIndex, 10);
  var field = el.dataset.field;
  if (isNaN(idx) || !field) return;

  function update() {
    var ib = state.editorDraft.inbounds[idx];
    if (!ib) return;

    if (el.type === "checkbox") {
      ib[field] = el.checked;
    } else if (field === "fixed_ports_text") {
      ib.fixed_ports = parsePorts(el.value);
    } else if (field === "random_count") {
      ib.random_count = Math.max(1, Number(el.value) || 1);
    } else if (field === "port_mode") {
      ib.port_mode = el.value;
      var cont = $("#inboundEditorList");
      if (cont) {
        var fixEl = cont.querySelector('[data-in-fixed="' + idx + '"]');
        var rndEl = cont.querySelector('[data-in-random="' + idx + '"]');
        var isFix = el.value !== "random";
        if (fixEl) fixEl.style.display = isFix ? "" : "none";
        if (rndEl) rndEl.style.display = !isFix ? "" : "none";
      }
      renderRoutingEditor();
    } else {
      ib[field] = el.value;
    }

    if (field === "name") {
      var card = el.closest(".editor-card");
      if (card) {
        var titleEl = card.querySelector(".editor-card-title-main");
        if (titleEl)
          titleEl.textContent =
            "Inbound " + (idx + 1) + ": " + (el.value || "Unnamed");
      }
      renderRoutingEditor();
      renderBalancerEditor();
    }
  }

  el.addEventListener("input", update);
  el.addEventListener("change", update);
}

// --- Routing Editor ---

function renderRoutingEditor() {
  var container = $("#routingEditorList");
  if (!container || !state.editorDraft) return;
  var inbounds = state.editorDraft.inbounds || [];
  var aliases = currentBalancerAliases();

  if (!inbounds.length) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = inbounds
    .map(function (ib, i) {
      var portSummary =
        ib.port_mode === "random"
          ? (ib.random_count || 1) + " random port(s)"
          : portsToText(ib.fixed_ports) || "No ports";
      var isStatic = ib.target_type !== "balancer";
      var isOpen = isEditorCardOpen("routing", i);

      var balOpts = aliases
        .map(function (a) {
          return (
            '<option value="' +
            escapeHtml(a) +
            '"' +
            (ib.target_balancer === a ? " selected" : "") +
            ">" +
            escapeHtml(a) +
            "</option>"
          );
        })
        .join("");

      return (
        '<div class="editor-card editor-card--collapsible' +
        (isOpen ? " is-open" : " is-collapsed") +
        '" data-rt-index="' +
        i +
        '">' +
        '<div class="editor-card-header">' +
        '<div class="editor-card-heading">' +
        editorCollapseButton("routing", i, isOpen, "Toggle routing") +
        '<span class="editor-card-title"><span class="editor-card-title-main">' +
        escapeHtml(ib.name || "Inbound " + (i + 1)) +
        " — " +
        escapeHtml(portSummary) +
        "</span></span>" +
        "</div>" +
        "</div>" +
        '<div class="editor-card-body">' +
        '<div class="form-row"><div class="form-group"><label>Target Type</label>' +
        '<select class="form-input" data-rt-index="' +
        i +
        '" data-field="target_type">' +
        '<option value="static"' +
        (isStatic ? " selected" : "") +
        ">Static</option>" +
        '<option value="balancer"' +
        (!isStatic ? " selected" : "") +
        ">Balancer</option>" +
        "</select></div></div>" +
        '<div class="form-row"' +
        (!isStatic ? ' style="display:none"' : "") +
        ' data-rt-static="' +
        i +
        '">' +
        '<div class="form-group"><label>Target Host</label>' +
        '<input type="text" class="form-input" data-rt-index="' +
        i +
        '" data-field="target_host" value="' +
        escapeHtml(ib.target_host || "") +
        '"></div>' +
        '<div class="form-group"><label>Target Port</label>' +
        '<input type="text" class="form-input" data-rt-index="' +
        i +
        '" data-field="target_port" value="' +
        escapeHtml(String(ib.target_port || "")) +
        '"></div>' +
        "</div>" +
        '<div class="form-row"' +
        (isStatic ? ' style="display:none"' : "") +
        ' data-rt-balancer="' +
        i +
        '">' +
        '<div class="form-group"><label>Balancer</label>' +
        '<select class="form-input" data-rt-index="' +
        i +
        '" data-field="target_balancer">' +
        '<option value="">— Select Balancer —</option>' +
        balOpts +
        "</select></div>" +
        "</div>" +
        '<div class="form-row"><div class="form-group"><label>Notes</label>' +
        '<input type="text" class="form-input" data-rt-index="' +
        i +
        '" data-field="notes" value="' +
        escapeHtml(ib.notes || "") +
        '"></div>' +
        "</div>" +
        "</div>" +
        "</div>"
      );
    })
    .join("");

  bindEditorCardToggles(container);
  container.querySelectorAll("[data-rt-index]").forEach(function (el) {
    function update() {
      var idx = parseInt(el.dataset.rtIndex, 10);
      var field = el.dataset.field;
      var ib = state.editorDraft.inbounds[idx];
      if (!ib) return;
      if (field === "target_type") {
        ib.target_type = el.value;
        var isStatic = el.value !== "balancer";
        var stRow = container.querySelector('[data-rt-static="' + idx + '"]');
        var blRow = container.querySelector('[data-rt-balancer="' + idx + '"]');
        if (stRow) stRow.style.display = isStatic ? "" : "none";
        if (blRow) blRow.style.display = !isStatic ? "" : "none";
      } else if (field) {
        ib[field] = el.value;
      }
    }
    if (el.dataset.field) {
      el.addEventListener("input", update);
      el.addEventListener("change", update);
    }
  });
}

// --- Balancer Editor ---

function renderBalancerEditor() {
  var container = $("#balancerEditorList");
  if (!container || !state.editorDraft) return;
  var balancers = state.editorDraft.balancers || [];

  if (!balancers.length) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = balancers
    .map(function (bal, i) {
      var endpointCount = Array.isArray(bal.endpoints) ? bal.endpoints.length : 0;
      var isOpen = isEditorCardOpen("balancer", i);
      return (
        '<div class="editor-card editor-card--collapsible balancer-tree-card' +
        (isOpen ? " is-open" : " is-collapsed") +
        '" data-bal-index="' +
        i +
        '">' +
        '<div class="editor-card-header balancer-tree-header">' +
        '<div class="editor-card-heading">' +
        editorCollapseButton("balancer", i, isOpen, "Toggle balancer") +
        '<span class="editor-card-title"><i class="fa-solid fa-scale-balanced" aria-hidden="true"></i> <span class="editor-card-title-main">Balancer ' +
        (i + 1) +
        ": " +
        escapeHtml(bal.alias || "Unnamed") +
        '</span> <span class="badge mini-badge">' + endpointCount + " endpoint" + (endpointCount === 1 ? "" : "s") + "</span></span>" +
        "</div>" +
        '<button class="btn btn-xs btn-danger btn-remove-soft" data-bal-index="' +
        i +
        '" data-action="remove-balancer" aria-label="Remove balancer">' +
        '<i class="fa-solid fa-trash-can" aria-hidden="true"></i><span>Remove</span></button>' +
        "</div>" +
        '<div class="editor-card-body">' +
        '<div class="form-row">' +
        '<div class="form-group"><label>Alias</label>' +
        '<input type="text" class="form-input" data-bal-index="' +
        i +
        '" data-field="alias" value="' +
        escapeHtml(bal.alias || "") +
        '"></div>' +
        '<div class="form-group"><label>Strategy</label>' +
        '<select class="form-input" data-bal-index="' +
        i +
        '" data-field="strategy">' +
        '<option value="round_robin"' +
        (bal.strategy === "round_robin" ? " selected" : "") +
        ">Round Robin</option>" +
        '<option value="random"' +
        (bal.strategy === "random" ? " selected" : "") +
        ">Random</option>" +
        '<option value="failover"' +
        (bal.strategy === "failover" ? " selected" : "") +
        ">Failover</option>" +
        '<option value="least_connections"' +
        (bal.strategy === "least_connections" ? " selected" : "") +
        ">Least Connections</option>" +
        "</select></div>" +
        '<div class="form-group form-group--inline switch-field">' +
        '<label class="toggle-label toggle-label--inline toggle-label--state" for="balEnabled_' +
        i +
        '">' +
        '<input type="checkbox" class="toggle-input" id="balEnabled_' +
        i +
        '" data-bal-index="' +
        i +
        '" data-field="enabled"' +
        (bal.enabled !== false ? " checked" : "") +
        ">" +
        '<span class="toggle-track" aria-hidden="true"><span class="toggle-thumb"></span></span>' +
        '<span class="toggle-text">Enabled</span></label></div>' +
        "</div>" +
        '<div class="form-row"><div class="form-group"><label>Notes</label>' +
        '<input type="text" class="form-input" data-bal-index="' +
        i +
        '" data-field="notes" value="' +
        escapeHtml(bal.notes || "") +
        '"></div>' +
        "</div>" +
        '<div class="endpoints-section endpoints-tree-section">' +
        '<div class="endpoints-header endpoints-header--clean">' +
        '<span><i class="fa-solid fa-diagram-project" aria-hidden="true"></i> Endpoints</span>' +
        "</div>" +
        '<div class="endpoints-list endpoint-tree" id="endpointList_' +
        i +
        '"></div>' +
        '<div class="endpoints-footer">' +
        '<button class="btn btn-sm btn-primary endpoint-add-bottom" data-bal-index="' +
        i +
        '" data-action="add-endpoint"><i class="fa-solid fa-plus" aria-hidden="true"></i><span>Add Endpoint</span></button>' +
        "</div>" +
        "</div>" +
        "</div>" +
        "</div>"
      );
    })
    .join("");

  bindEditorCardToggles(container);
  container.querySelectorAll("[data-bal-index]").forEach(function (el) {
    var action = el.dataset.action;
    if (action === "remove-balancer") {
      el.addEventListener("click", function () {
        state.editorDraft.balancers.splice(parseInt(el.dataset.balIndex, 10), 1);
        renderCoreEditor();
      });
    } else if (action === "add-endpoint") {
      el.addEventListener("click", function () {
        var idx = parseInt(el.dataset.balIndex, 10);
        if (!Array.isArray(state.editorDraft.balancers[idx].endpoints)) {
          state.editorDraft.balancers[idx].endpoints = [];
        }
        var ep = defaultEndpoint();
        state.editorDraft.balancers[idx].endpoints.push(ep);
        state.endpointOpen[idx + ":" + (state.editorDraft.balancers[idx].endpoints.length - 1)] = true;
        state.editorCardOpen[editorCardKey("balancer", idx)] = true;
        renderBalancerEditor();
      });
    } else if (el.tagName !== "BUTTON" && el.dataset.field) {
      (function () {
        var balIdx = parseInt(el.dataset.balIndex, 10);
        var field = el.dataset.field;
        function update() {
          var bal = state.editorDraft.balancers[balIdx];
          if (!bal) return;
          if (el.type === "checkbox") bal[field] = el.checked;
          else bal[field] = el.value;
          if (field === "alias") {
            var card = el.closest(".editor-card");
            if (card) {
              var titleEl = card.querySelector(".editor-card-title-main");
              if (titleEl) titleEl.textContent = "Balancer " + (balIdx + 1) + ": " + (el.value || "Unnamed");
            }
            renderRoutingEditor();
          }
        }
        el.addEventListener("input", update);
        el.addEventListener("change", update);
      })();
    }
  });

  balancers.forEach(function (_, i) {
    renderEndpointList(i);
  });
}

function endpointKey(balancerIndex, endpointIndex) {
  return String(balancerIndex) + ":" + String(endpointIndex);
}

function endpointTitle(ep, index) {
  if (!ep) return "Endpoint " + (index + 1);
  if (ep.type === "node_inbound") {
    var node = nodeById(ep.node_id);
    var inbound = ep.inbound_name || "Select inbound";
    return (inbound || "Node inbound") + " → " + (node ? nodeDisplayName(node) : "Select node");
  }
  return (ep.host || "Static target") + ":" + (ep.port || "port");
}

function endpointSubTitle(ep) {
  if (!ep) return "";
  if (ep.type === "node_inbound") {
    return "Node inbound" + (ep.weight ? " · weight " + ep.weight : "");
  }
  return "Static" + (ep.weight ? " · weight " + ep.weight : "");
}

function inboundOptionLabel(item) {
  var name = item.inbound_name || item.name || "Unnamed inbound";
  var coreName = item.core_name || (state.editingCore && state.editingCore.name) || "Current core";
  var ports = Array.isArray(item.ports) && item.ports.length ? " · " + item.ports.join(",") : "";
  return coreName + " / " + name + ports;
}

function endpointInboundOptions(nodeId) {
  nodeId = String(nodeId || "");
  var options = [];
  var seen = {};

  function addOption(item) {
    var name = String(item.inbound_name || item.name || "").trim();
    if (!name) return;
    var key = String(item.core_id || "") + "::" + name;
    if (seen[key]) return;
    seen[key] = true;
    options.push({
      name: name,
      core_id: item.core_id || "",
      node_id: item.node_id || nodeId,
      label: inboundOptionLabel(item),
      ports: Array.isArray(item.ports) ? item.ports : [],
      public_host: item.public_host || "",
      bind_ip: item.bind_ip || "",
    });
  }

  if (state.editorDraft && String(state.editorDraft.node_id || "") === nodeId) {
    (state.editorDraft.inbounds || []).forEach(function (ib) {
      addOption({
        core_id: state.editingCore ? state.editingCore.id : "",
        core_name: state.editorDraft.name || (state.editingCore && state.editingCore.name) || "Current core",
        node_id: nodeId,
        inbound_name: ib.name,
        ports: ib.port_mode === "fixed" ? (ib.fixed_ports || []) : [],
        public_host: ib.public_host || "",
        bind_ip: ib.bind_ip || "",
      });
    });
  }

  (state.inboundCatalog || [])
    .filter(function (ib) { return String(ib.node_id || "") === nodeId; })
    .forEach(addOption);

  return options;
}

function fillEndpointInboundSelect(select, nodeId, value, coreId) {
  value = value || "";
  coreId = coreId || "";
  nodeId = nodeId || "";
  if (!select) return;
  var options = endpointInboundOptions(nodeId);
  var html = '<option value="">— Select Inbound —</option>';
  html += options
    .map(function (item) {
      var selected = item.name === value && (!coreId || !item.core_id || String(item.core_id) === String(coreId));
      return (
        '<option value="' +
        escapeHtml(item.name) +
        '" data-core-id="' +
        escapeHtml(item.core_id || "") +
        '" data-ports="' +
        escapeHtml((item.ports || []).join(",")) +
        '"' +
        (selected ? " selected" : "") +
        ">" +
        escapeHtml(item.label || item.name) +
        "</option>"
      );
    })
    .join("");
  if (value && !options.some(function (item) { return item.name === value; })) {
    html += '<option value="' + escapeHtml(value) + '" selected>' + escapeHtml(value + " (missing)") + "</option>";
  }
  select.innerHTML = html;
}

function applyEndpointInboundSelection(ep, select) {
  if (!ep || !select) return;
  var opt = select.options[select.selectedIndex];
  ep.inbound_name = select.value;
  ep.core_id = opt ? (opt.getAttribute("data-core-id") || "") : "";
  var ports = opt ? String(opt.getAttribute("data-ports") || "") : "";
  var firstPort = ports.split(",").map(function (p) { return parseInt(p.trim(), 10); }).filter(function (p) { return p >= 1 && p <= 65535; })[0];
  if (firstPort) ep.port = firstPort;
  if (!ep.host) ep.host = "127.0.0.1";
}

function renderEndpointList(balancerIndex) {
  var container = $("#endpointList_" + balancerIndex);
  if (!container) return;
  var bal = state.editorDraft.balancers[balancerIndex];
  if (!bal) return;
  if (!Array.isArray(bal.endpoints)) bal.endpoints = [];
  var endpoints = bal.endpoints;

  if (!endpoints.length) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = endpoints
    .map(function (ep, j) {
      var isStatic = ep.type !== "node_inbound";
      var key = endpointKey(balancerIndex, j);
      var isOpen = state.endpointOpen[key] !== false;
      return (
        '<div class="endpoint-tree-item" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '">' +
        '<div class="endpoint-tree-rail" aria-hidden="true"><span></span></div>' +
        '<div class="endpoint-card endpoint-card--tree' +
        (isOpen ? " is-open" : " is-collapsed") +
        '" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '">' +
        '<div class="endpoint-card-header endpoint-card-header--tree">' +
        '<button type="button" class="endpoint-collapse-btn" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '" data-action="toggle-ep" aria-label="Toggle endpoint">' +
        '<i class="fa-solid ' + (isOpen ? "fa-chevron-down" : "fa-chevron-right") + '" aria-hidden="true"></i></button>' +
        '<div class="endpoint-title-wrap"><strong>Endpoint ' +
        (j + 1) +
        '</strong><span>' +
        escapeHtml(endpointTitle(ep, j)) +
        '</span><small>' +
        escapeHtml(endpointSubTitle(ep)) +
        '</small></div>' +
        '<button class="btn btn-xs btn-danger btn-remove-soft" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '" data-action="remove-ep" aria-label="Remove endpoint">' +
        '<i class="fa-solid fa-trash-can" aria-hidden="true"></i><span>Remove</span></button>' +
        "</div>" +
        '<div class="endpoint-card-body">' +
        '<div class="form-row">' +
        '<div class="form-group"><label>Type</label>' +
        '<select class="form-input ep-field" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '" data-field="type">' +
        '<option value="static"' +
        (isStatic ? " selected" : "") +
        ">Static</option>" +
        '<option value="node_inbound"' +
        (!isStatic ? " selected" : "") +
        ">Node Inbound</option>" +
        "</select></div>" +
        '<div class="form-group"' +
        (!isStatic ? ' style="display:none"' : "") +
        ' data-ep-static-g="' +
        balancerIndex +
        "-" +
        j +
        '"><label>Host</label>' +
        '<input type="text" class="form-input ep-field" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '" data-field="host" value="' +
        escapeHtml(ep.host || "") +
        '"></div>' +
        '<div class="form-group"' +
        (!isStatic ? ' style="display:none"' : "") +
        ' data-ep-sport-g="' +
        balancerIndex +
        "-" +
        j +
        '"><label>Port</label>' +
        '<input type="number" class="form-input ep-field" min="1" max="65535" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '" data-field="port" value="' +
        escapeHtml(String(ep.port || 80)) +
        '"></div>' +
        "</div>" +
        '<div class="form-row"' +
        (isStatic ? ' style="display:none"' : "") +
        ' data-ep-ni-g="' +
        balancerIndex +
        "-" +
        j +
        '">' +
        '<div class="form-group"><label>Node</label>' +
        '<select class="form-input ep-field ep-node-sel" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '" data-field="node_id"></select></div>' +
        '<div class="form-group"><label>Inbound</label>' +
        '<select class="form-input ep-field ep-inb-sel" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '" data-field="inbound_name"></select></div>' +
        "</div>" +
        '<div class="form-row">' +
        '<div class="form-group"><label>Weight</label>' +
        '<input type="number" class="form-input ep-field" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '" data-field="weight" min="1" value="' +
        escapeHtml(String(ep.weight || 1)) +
        '"></div>' +
        '<div class="form-group"><label>Certificate</label>' +
        '<input type="text" class="form-input ep-field" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '" data-field="certificate" value="' +
        escapeHtml(ep.certificate || "") +
        '"></div>' +
        '<div class="form-group form-group--inline switch-field">' +
        '<label class="toggle-label toggle-label--inline toggle-label--state" for="epEnabled_' +
        balancerIndex +
        "_" +
        j +
        '">' +
        '<input type="checkbox" id="epEnabled_' +
        balancerIndex +
        "_" +
        j +
        '" class="ep-field toggle-input" data-ep-bal="' +
        balancerIndex +
        '" data-ep-index="' +
        j +
        '" data-field="enabled"' +
        (ep.enabled !== false ? " checked" : "") +
        ">" +
        '<span class="toggle-track" aria-hidden="true"><span class="toggle-thumb"></span></span>' +
        '<span class="toggle-text">Enabled</span></label></div>' +
        "</div>" +
        "</div>" +
        "</div>" +
        "</div>"
      );
    })
    .join("");

  container.querySelectorAll(".ep-node-sel").forEach(function (sel) {
    var j = parseInt(sel.dataset.epIndex, 10);
    var ep = bal.endpoints[j];
    fillEndpointNodeSelect(sel, ep ? ep.node_id : "");
  });
  container.querySelectorAll(".ep-inb-sel").forEach(function (sel) {
    var j = parseInt(sel.dataset.epIndex, 10);
    var ep = bal.endpoints[j];
    fillEndpointInboundSelect(
      sel,
      ep ? ep.node_id : "",
      ep ? ep.inbound_name : "",
      ep ? ep.core_id : "",
    );
  });

  container.querySelectorAll('[data-action="toggle-ep"]').forEach(function (btn) {
    btn.addEventListener("click", function () {
      var bi = parseInt(btn.dataset.epBal, 10);
      var j = parseInt(btn.dataset.epIndex, 10);
      var key = endpointKey(bi, j);
      state.endpointOpen[key] = state.endpointOpen[key] === false;
      renderEndpointList(bi);
    });
  });

  container
    .querySelectorAll('[data-action="remove-ep"]')
    .forEach(function (btn) {
      btn.addEventListener("click", function () {
        var bi = parseInt(btn.dataset.epBal, 10);
        var j = parseInt(btn.dataset.epIndex, 10);
        state.editorDraft.balancers[bi].endpoints.splice(j, 1);
        delete state.endpointOpen[endpointKey(bi, j)];
        renderBalancerEditor();
      });
    });

  container.querySelectorAll(".ep-field").forEach(function (el) {
    (function () {
      var bi = parseInt(el.dataset.epBal, 10);
      var j = parseInt(el.dataset.epIndex, 10);
      var field = el.dataset.field;
      function bindEp() {
        var ep = state.editorDraft.balancers[bi].endpoints[j];
        if (!ep) return;
        if (el.type === "checkbox") {
          ep[field] = el.checked;
        } else if (field === "weight") {
          ep.weight = Math.max(1, Number(el.value) || 1);
        } else if (field === "port") {
          ep.port = Math.max(1, Math.min(65535, Number(el.value) || 80));
        } else if (field === "node_id") {
          ep.node_id = el.value;
          ep.core_id = "";
          ep.inbound_name = "";
          if (!ep.host) ep.host = "127.0.0.1";
          if (!Number(ep.port)) ep.port = 80;
          var niG = container.querySelector(
            '[data-ep-ni-g="' + bi + "-" + j + '"]',
          );
          if (niG) {
            var inbSel = niG.querySelector(".ep-inb-sel");
            if (inbSel) fillEndpointInboundSelect(inbSel, el.value, "", "");
          }
        } else if (field === "inbound_name") {
          applyEndpointInboundSelection(ep, el);
        } else if (field === "type") {
          ep.type = el.value;
          var isSt = el.value !== "node_inbound";
          if (!isSt) {
            if (!ep.node_id && state.editorDraft && isValidNodeId(state.editorDraft.node_id)) ep.node_id = state.editorDraft.node_id;
            if (!Number(ep.port)) ep.port = 80;
            if (!ep.host) ep.host = "127.0.0.1";
          }
          var stG = container.querySelector(
            '[data-ep-static-g="' + bi + "-" + j + '"]',
          );
          var spG = container.querySelector(
            '[data-ep-sport-g="' + bi + "-" + j + '"]',
          );
          var niG2 = container.querySelector(
            '[data-ep-ni-g="' + bi + "-" + j + '"]',
          );
          if (stG) stG.style.display = isSt ? "" : "none";
          if (spG) spG.style.display = isSt ? "" : "none";
          if (niG2) niG2.style.display = !isSt ? "" : "none";
          renderEndpointList(bi);
        } else {
          ep[field] = el.value;
        }

        var card = el.closest(".endpoint-card");
        if (card) {
          var wrap = card.querySelector(".endpoint-title-wrap");
          if (wrap) {
            wrap.innerHTML = '<strong>Endpoint ' + (j + 1) + '</strong><span>' + escapeHtml(endpointTitle(ep, j)) + '</span><small>' + escapeHtml(endpointSubTitle(ep)) + '</small>';
          }
        }
      }
      el.addEventListener("input", bindEp);
      el.addEventListener("change", bindEp);
    })();
  });
}

function fillEndpointNodeSelect(select, value) {
  value = value || "";
  if (!select) return;
  select.innerHTML =
    '<option value="">— Select Node —</option>' +
    state.nodes
      .filter(function (n) { return isValidNodeId(n && n.id); })
      .map(function (n) {
        return (
          '<option value="' +
          escapeHtml(String(n.id)) +
          '"' +
          (String(n.id) === String(value) ? " selected" : "") +
          ">" +
          escapeHtml(nodeDisplayName(n)) +
          "</option>"
        );
      })
      .join("");
}

// --- Dependency Editor ---

function renderDependencyEditor() {
  var container = $("#dependencyEditorList");
  if (!container || !state.editorDraft) return;
  var deps = state.editorDraft.dependencies || [];

  if (!deps.length) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = deps
    .map(function (dep, i) {
      var isOpen = isEditorCardOpen("dependency", i);
      return (
        '<div class="editor-card editor-card--collapsible' +
        (isOpen ? " is-open" : " is-collapsed") +
        '" data-dep-index="' +
        i +
        '">' +
        '<div class="editor-card-header">' +
        '<div class="editor-card-heading">' +
        editorCollapseButton("dependency", i, isOpen, "Toggle dependency") +
        '<span class="editor-card-title"><span class="editor-card-title-main">Dependency ' +
        (i + 1) +
        '</span></span>' +
        "</div>" +
        '<button class="btn btn-xs btn-danger btn-remove-soft" data-dep-index="' +
        i +
        '" data-action="remove-dep" aria-label="Remove dependency">' +
        '<i class="fa-solid fa-trash-can" aria-hidden="true"></i><span>Remove</span></button>' +
        "</div>" +
        '<div class="editor-card-body">' +
        '<div class="form-row">' +
        '<div class="form-group"><label>Type</label>' +
        '<select class="form-input" data-dep-index="' +
        i +
        '" data-field="type">' +
        '<option value="core"' +
        (dep.type === "core" ? " selected" : "") +
        ">Core</option>" +
        '<option value="node"' +
        (dep.type === "node" ? " selected" : "") +
        ">Node</option>" +
        "</select></div>" +
        '<div class="form-group"><label>Reference</label>' +
        '<select class="form-input dep-ref-sel" data-dep-index="' +
        i +
        '" data-field="ref_id">' +
        dependencyOptions(dep.type, dep.ref_id) +
        "</select></div>" +
        '<div class="form-group form-group--inline switch-field">' +
        '<label class="toggle-label toggle-label--inline toggle-label--state" for="depReq_' +
        i +
        '">' +
        '<input type="checkbox" class="toggle-input" id="depReq_' +
        i +
        '" data-dep-index="' +
        i +
        '" data-field="required"' +
        (dep.required !== false ? " checked" : "") +
        ">" +
        '<span class="toggle-track" aria-hidden="true"><span class="toggle-thumb"></span></span>' +
        '<span class="toggle-text">Required</span></label></div>' +
        "</div>" +
        '<div class="form-row"><div class="form-group"><label>Notes</label>' +
        '<input type="text" class="form-input" data-dep-index="' +
        i +
        '" data-field="notes" value="' +
        escapeHtml(dep.notes || "") +
        '"></div>' +
        "</div>" +
        "</div>" +
        "</div>"
      );
    })
    .join("");

  bindEditorCardToggles(container);
  container.querySelectorAll("[data-dep-index]").forEach(function (el) {
    if (el.dataset.action === "remove-dep") {
      el.addEventListener("click", function () {
        state.editorDraft.dependencies.splice(parseInt(el.dataset.depIndex, 10), 1);
        renderDependencyEditor();
      });
    } else if (el.dataset.field) {
      (function () {
        var depIdx = parseInt(el.dataset.depIndex, 10);
        var field = el.dataset.field;
        function update() {
          var dep = state.editorDraft.dependencies[depIdx];
          if (!dep) return;
          if (el.type === "checkbox") dep[field] = el.checked;
          else dep[field] = el.value;
          if (field === "type") {
            dep.ref_id = "";
            var card = el.closest("[data-dep-index]");
            if (card) {
              var refSel = card.querySelector(".dep-ref-sel");
              if (refSel) refSel.innerHTML = dependencyOptions(el.value, "");
            }
          }
        }
        el.addEventListener("input", update);
        el.addEventListener("change", update);
      })();
    }
  });
}

function dependencyOptions(type, selected) {
  selected = selected || "";
  if (type === "node") {
    return state.nodes
      .map(function (n) {
        return (
          '<option value="' +
          escapeHtml(String(n.id)) +
          '"' +
          (String(n.id) === String(selected) ? " selected" : "") +
          ">" +
          escapeHtml(nodeDisplayName(n)) +
          "</option>"
        );
      })
      .join("");
  }
  var currentId = state.editingCore ? state.editingCore.id : null;
  return state.cores
    .filter(function (c) {
      return c.id !== currentId;
    })
    .map(function (c) {
      return (
        '<option value="' +
        escapeHtml(String(c.id)) +
        '"' +
        (String(c.id) === String(selected) ? " selected" : "") +
        ">" +
        escapeHtml(c.name || "Core #" + c.id) +
        "</option>"
      );
    })
    .join("");
}

// --- Advanced JSON Editor ---

function renderAdvancedEditor() {
  if (!state.editorDraft) return;
  var cfg = ensureAdvancedConfig(state.editorDraft);
  var enabled = $("#advancedJsonEnabled");
  var textarea = $("#advancedJsonEditor");
  var result = $("#advancedValidationResult");
  if (enabled) enabled.checked = !!cfg.enabled;
  if (textarea && textarea.value !== cfg.json_config) textarea.value = cfg.json_config || "";
  if (result && !result.dataset.keep) result.innerHTML = "";
}

function syncAdvancedEditorToDraft() {
  if (!state.editorDraft) return;
  var cfg = ensureAdvancedConfig(state.editorDraft);
  var enabled = $("#advancedJsonEnabled");
  var textarea = $("#advancedJsonEditor");
  if (enabled) cfg.enabled = !!enabled.checked;
  if (textarea) cfg.json_config = textarea.value || "";
}

function showAdvancedValidation(result, type) {
  var box = $("#advancedValidationResult");
  if (!box) return;
  type = type || "info";
  box.className = "advanced-validation advanced-validation--" + type;
  box.dataset.keep = "1";
  if (Array.isArray(result)) {
    box.innerHTML = result.map(function (line) { return '<div>' + escapeHtml(line) + '</div>'; }).join("");
  } else {
    box.textContent = String(result || "");
  }
}

function validateAdvancedJsonLocally() {
  syncAdvancedEditorToDraft();
  var cfg = ensureAdvancedConfig(state.editorDraft);
  var text = String(cfg.json_config || "").trim();
  if (!text) return { ok: true, value: null, warnings: ["Manual JSON is empty."] };
  try {
    var value = JSON.parse(text);
    if (!value || Array.isArray(value) || typeof value !== "object") {
      return { ok: false, errors: ["JSON root must be an object."] };
    }
    return { ok: true, value: value, warnings: [] };
  } catch (err) {
    return { ok: false, errors: [err.message || "Invalid JSON syntax."] };
  }
}

async function validateAdvancedConfig(options) {
  options = options || {};
  var btn = $("#validateAdvancedJsonButton");
  var local = validateAdvancedJsonLocally();
  if (!local.ok) {
    showAdvancedValidation(local.errors || ["Invalid JSON."], "error");
    if (!options.silent) showToast("Advanced JSON is invalid.", "error");
    return false;
  }
  syncAdvancedEditorToDraft();
  var cfg = ensureAdvancedConfig(state.editorDraft);
  if (!cfg.enabled || !String(cfg.json_config || "").trim()) {
    showAdvancedValidation(cfg.enabled ? "Manual JSON is empty." : "Manual JSON override is disabled.", "info");
    return true;
  }
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin" aria-hidden="true"></i> Validating';
  }
  try {
    var data = await api("/api/cores/advanced/validate", {
      method: "POST",
      body: JSON.stringify({ json_config: cfg.json_config }),
    });
    var lines = [];
    if (data.valid) lines.push("JSON is valid.");
    (data.errors || []).forEach(function (x) { lines.push("Error: " + x); });
    (data.warnings || []).forEach(function (x) { lines.push("Warning: " + x); });
    showAdvancedValidation(lines, data.valid ? "success" : "error");
    if (!options.silent) showToast(data.valid ? "Advanced JSON is valid." : "Advanced JSON has errors.", data.valid ? "success" : "error");
    return !!data.valid;
  } catch (err) {
    showAdvancedValidation(err.message || "Validation failed.", "error");
    if (!options.silent) showToast(err.message || "Validation failed.", "error");
    return false;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="fa-solid fa-shield-halved" aria-hidden="true"></i> Validate JSON';
    }
  }
}


function sanitizeCorePayload(payload) {
  payload = payload || {};
  (payload.balancers || []).forEach(function (bal) {
    if (!Array.isArray(bal.endpoints)) bal.endpoints = [];
    bal.endpoints.forEach(function (ep) {
      ep.type = ep.type === "node_inbound" ? "node_inbound" : "static";
      ep.weight = Math.max(0, Number(ep.weight) || 1);
      if (ep.type === "node_inbound") {
        if (!ep.host) ep.host = "127.0.0.1";
        ep.port = Math.max(1, Math.min(65535, Number(ep.port) || 80));
        ep.node_id = String(ep.node_id || "");
        ep.core_id = String(ep.core_id || "");
        ep.inbound_name = String(ep.inbound_name || "");
      } else {
        ep.host = String(ep.host || "127.0.0.1").trim() || "127.0.0.1";
        ep.port = Math.max(1, Math.min(65535, Number(ep.port) || 80));
        ep.node_id = "";
        ep.core_id = "";
        ep.inbound_name = "";
      }
    });
  });
  return payload;
}

function validateEditorBalancerEndpoints(payload) {
  var errors = [];
  (payload.balancers || []).forEach(function (bal, bi) {
    (bal.endpoints || []).forEach(function (ep, ei) {
      if (ep.type === "node_inbound") {
        if (!isValidNodeId(ep.node_id)) errors.push("Balancer " + (bi + 1) + ", endpoint " + (ei + 1) + ": select a valid node.");
        if (!String(ep.inbound_name || "").trim()) errors.push("Balancer " + (bi + 1) + ", endpoint " + (ei + 1) + ": select an inbound.");
      } else {
        if (!String(ep.host || "").trim()) errors.push("Balancer " + (bi + 1) + ", endpoint " + (ei + 1) + ": target host is required.");
        if (!(Number(ep.port) >= 1 && Number(ep.port) <= 65535)) errors.push("Balancer " + (bi + 1) + ", endpoint " + (ei + 1) + ": target port must be between 1 and 65535.");
      }
    });
  });
  return errors;
}

function collectEditorPayload() {
  syncEditorHeaderToDraft();
  var d = state.editorDraft;
  return sanitizeCorePayload({
    name: d.name,
    node_id: d.node_id,
    enabled: d.enabled,
    inbounds: d.inbounds || [],
    balancers: d.balancers || [],
    dependencies: d.dependencies || [],
    advanced_config: ensureAdvancedConfig(d),
  });
}

async function saveCoreEditor() {
  if (!state.editingCore) return false;
  if (!isValidCoreId(state.editingCore.id)) { warnInvalidIdentifier("core"); await refreshAll(); return false; }
  var payload = collectEditorPayload();
  if (!isValidNodeId(payload.node_id)) { showToast("Select a valid node before saving this core.", "warning"); return false; }
  var endpointErrors = validateEditorBalancerEndpoints(payload);
  if (endpointErrors.length) { showToast(endpointErrors[0], "warning"); return false; }
  if (payload.advanced_config && payload.advanced_config.enabled) {
    var advancedOk = await validateAdvancedConfig({ silent: true });
    if (!advancedOk) return false;
    payload = collectEditorPayload();
  }
  var saveBtns = $$("#saveCoreBtn, #saveCoreEditorBottom");
  saveBtns.forEach(function (b) {
    b.disabled = true;
    b.textContent = "Saving\u2026";
  });

  try {
    var data = await api("/api/cores/" + encodeURIComponent(state.editingCore.id), {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    if (data.ok) {
      state.editingCore = data.core;
      state.editorDraft = deepCopy(data.core);
      if (!Array.isArray(state.editorDraft.inbounds))
        state.editorDraft.inbounds = [];
      if (!Array.isArray(state.editorDraft.balancers))
        state.editorDraft.balancers = [];
      if (!Array.isArray(state.editorDraft.dependencies))
        state.editorDraft.dependencies = [];
      ensureAdvancedConfig(state.editorDraft);
      showToast("Core saved successfully.", "success");
      await refreshAll();
      bindCoreEditorHeader();
      updateTabBadges();
      return true;
    }
    return false;
  } catch (err) {
    showToast(err.message || "Failed to save core.", "error");
    return false;
  } finally {
    saveBtns.forEach(function (b) {
      b.disabled = false;
      b.textContent = "Save Core";
    });
  }
}

async function saveAndApplyCoreEditor() {
  if (!state.editingCore) return;
  var ok = await saveCoreEditor();
  if (!ok || !state.editingCore) return;
  await applyCore(state.editingCore.id, null);
}

// ============================================================
// 14. LOGS PAGE
// ============================================================

async function loadLogSources() {
  try {
    var data = await api("/api/logs/sources");
    if (data.ok) {
      state.logSources = data.sources || [];
      var select = $("#logSourceSelect");
      if (!select) return;
      var prev = select.value || state.currentLogSource;
      select.innerHTML = state.logSources
        .map(function (src) {
          return (
            '<option value="' +
            escapeHtml(src.id) +
            '"' +
            (src.id === prev ? " selected" : "") +
            ">" +
            escapeHtml(src.label || src.id) +
            "</option>"
          );
        })
        .join("");
      if (!select.value && state.logSources.length)
        select.value = state.logSources[0].id;
      state.currentLogSource = select.value;
    }
  } catch (err) {
    console.error("loadLogSources:", err);
  }
}

function renderLogs(data) {
  var output = $("#logsOutput");
  var lineCount = $("#logsLineCount");
  if (!output) return;

  output.innerHTML = "";

  if (!data || data.error) {
    var errDiv = document.createElement("div");
    errDiv.className = "logs-error";
    errDiv.textContent = data
      ? data.error || "Failed to load logs."
      : "Failed to load logs.";
    output.appendChild(errDiv);
    if (lineCount) lineCount.textContent = "0 lines";
    return;
  }

  var lines = data.lines || [];
  if (lineCount)
    lineCount.textContent =
      lines.length + " line" + (lines.length !== 1 ? "s" : "");

  if (!lines.length) {
    var ph = document.createElement("div");
    ph.className = "logs-placeholder";
    ph.textContent = "No log lines found.";
    output.appendChild(ph);
    return;
  }

  var frag = document.createDocumentFragment();
  lines.forEach(function (line) {
    frag.appendChild(colorizeLogLine(line));
  });
  output.appendChild(frag);
  output.scrollTop = output.scrollHeight;
}

function colorizeLogLine(line) {
  var span = document.createElement("span");
  span.className = "log-line";

  var upper = line.toUpperCase();
  if (upper.indexOf("| CRITICAL |") !== -1 || upper.indexOf("CRITICAL") !== -1) {
    span.classList.add("log-level-critical");
  } else if (upper.indexOf("| ERROR |") !== -1 || upper.indexOf("| ERROR") !== -1 || upper.indexOf("TRACEBACK") !== -1) {
    span.classList.add("log-level-error");
  } else if (
    upper.indexOf("| WARNING |") !== -1 ||
    upper.indexOf("| WARN |") !== -1 ||
    upper.indexOf("WARNING") !== -1 ||
    upper.indexOf("WARN") !== -1
  ) {
    span.classList.add("log-level-warn");
  } else if (upper.indexOf("| DEBUG |") !== -1 || upper.indexOf("PANEL.REQUEST") !== -1 || upper.indexOf("NODE.REQUEST") !== -1 || upper.indexOf("NODE_API") !== -1) {
    span.classList.add("log-level-debug");
  } else if (upper.indexOf("| INFO |") !== -1) {
    span.classList.add("log-level-info");
  } else if (/\b(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+/.test(line)) {
    span.classList.add("log-level-access");
  } else if (upper.indexOf("SUCCESS") !== -1 || upper.indexOf("READY") !== -1) {
    span.classList.add("log-level-success");
  }

  var tsMatch = line.match(
    /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)/,
  );
  if (tsMatch) {
    var tsSpan = document.createElement("span");
    tsSpan.className = "log-ts";
    tsSpan.textContent = tsMatch[1];
    span.appendChild(tsSpan);
    span.appendChild(document.createTextNode(line.slice(tsMatch[1].length)));
  } else {
    span.textContent = line;
  }

  return span;
}

function clampLogRefreshInterval(value) {
  var num = Number(value);
  if (!Number.isFinite(num)) num = 10;
  num = Math.round(num);
  return Math.max(1, Math.min(num, 3600));
}

function getLogRefreshIntervalSeconds() {
  var input = $("#logRefreshIntervalInput");
  var seconds = clampLogRefreshInterval(input ? input.value : state.logRefreshIntervalSeconds);
  state.logRefreshIntervalSeconds = seconds;
  if (input && String(input.value) !== String(seconds)) input.value = String(seconds);
  try {
    localStorage.setItem("doctorDev.logRefreshIntervalSeconds", String(seconds));
  } catch (_) {}
  return seconds;
}

function updateLogAutoRefreshLabel(active) {
  var lastUpdEl = $("#logsLastUpdated");
  if (!lastUpdEl) return;
  if (active) {
    lastUpdEl.textContent =
      "Live refresh: every " + getLogRefreshIntervalSeconds() + " second" +
      (getLogRefreshIntervalSeconds() === 1 ? "" : "s");
  }
}

function stopLogAutoRefresh(uncheck) {
  if (state.logAutoRefreshTimer) {
    clearInterval(state.logAutoRefreshTimer);
    state.logAutoRefreshTimer = null;
  }
  if (uncheck) {
    var cb = $("#logAutoRefresh");
    if (cb) cb.checked = false;
  }
}

function startLogAutoRefresh() {
  stopLogAutoRefresh(false);
  var seconds = getLogRefreshIntervalSeconds();
  state.logAutoRefreshTimer = setInterval(function () {
    if (state.page === "logs") loadLogs({ silent: true });
  }, seconds * 1000);
  updateLogAutoRefreshLabel(true);
}

function syncLogAutoRefresh() {
  var cb = $("#logAutoRefresh");
  if (cb && cb.checked) startLogAutoRefresh();
  else stopLogAutoRefresh(false);
}

async function loadLogs(options) {
  options = options || {};
  if (state.logsLoading) return;
  state.logsLoading = true;
  var sourceEl = $("#logSourceSelect");
  var limitEl = $("#logLimitSelect");
  var levelEl = $("#logLevelSelect");
  var searchEl = $("#logSearchInput");
  var lastUpdEl = $("#logsLastUpdated");
  var refreshBtn = $("#refreshLogsBtn");

  var source = sourceEl ? sourceEl.value : state.currentLogSource;
  var limit = limitEl ? limitEl.value : "100";
  var level = levelEl ? levelEl.value : "";
  var q = searchEl ? searchEl.value.trim() : "";

  if (source) state.currentLogSource = source;
  if (refreshBtn) refreshBtn.disabled = true;

  try {
    var params =
      "source=" +
      encodeURIComponent(source) +
      "&limit=" +
      encodeURIComponent(limit);
    if (level) params += "&level=" + encodeURIComponent(level);
    if (q) params += "&q=" + encodeURIComponent(q);

    var data = await api("/api/logs?" + params);
    state.rawLogLines = data.lines || [];
    renderLogs(data);
    if (lastUpdEl)
      lastUpdEl.textContent = "Updated: " + new Date().toLocaleTimeString();
  } catch (err) {
    renderLogs(null);
    if (!options.silent) showToast(err.message || "Failed to load logs.", "error");
  } finally {
    if (refreshBtn) refreshBtn.disabled = false;
    state.logsLoading = false;
    var autoCb = $("#logAutoRefresh");
    if (autoCb && autoCb.checked) updateLogAutoRefreshLabel(true);
  }
}

// ============================================================
// 15. EVENT LISTENERS
// ============================================================

document.addEventListener("DOMContentLoaded", function () {
  // --- Auth ---
  var loginForm = $("#loginForm");
  if (loginForm) loginForm.addEventListener("submit", handleLoginSubmit);

  var logoutBtn = $("#logoutButton");
  if (logoutBtn) logoutBtn.addEventListener("click", handleLogout);

  var togglePwdBtn = $("#togglePassword");
  if (togglePwdBtn)
    togglePwdBtn.addEventListener("click", togglePasswordVisibility);

  // --- Navigation ---
  $$(".nav-item[data-page]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      switchPage(btn.dataset.page);
    });
  });

  // --- Dashboard quick actions ---
  var qaAddNode = $("#qaAddNode");
  if (qaAddNode)
    qaAddNode.addEventListener("click", function () {
      openNodeModal();
    });

  var qaAddCore = $("#qaAddCore");
  if (qaAddCore)
    qaAddCore.addEventListener("click", function () {
      openCoreCreateModal();
    });

  var qaViewLogs = $("#qaViewLogs");
  if (qaViewLogs)
    qaViewLogs.addEventListener("click", function () {
      switchPage("logs");
    });

  var qaManageNodes = $("#qaManageNodes");
  if (qaManageNodes)
    qaManageNodes.addEventListener("click", function () {
      switchPage("nodes");
    });

  // --- Refresh ---
  var refreshBtn = $("#refreshButton");
  if (refreshBtn) refreshBtn.addEventListener("click", refreshAll);
  var repairDataBtn = $("#repairDataButton");
  if (repairDataBtn) repairDataBtn.addEventListener("click", repairPanelData);

  // --- Nodes ---
  var createNodeBtn = $("#createNodeBtn");
  if (createNodeBtn)
    createNodeBtn.addEventListener("click", function () {
      openNodeModal();
    });

  var nodesEmptyCreate = $("#nodesEmptyCreateBtn");
  if (nodesEmptyCreate)
    nodesEmptyCreate.addEventListener("click", function () {
      openNodeModal();
    });

  var nodeModal = $("#nodeModal");
  if (nodeModal) {
    nodeModal.addEventListener("click", function (e) {
      if (e.target === nodeModal) closeNodeModal();
    });
  }

  var closeNodeModalBtn = $("#closeNodeModal");
  if (closeNodeModalBtn)
    closeNodeModalBtn.addEventListener("click", closeNodeModal);

  var cancelNodeBtn = $("#cancelNodeButton");
  if (cancelNodeBtn) cancelNodeBtn.addEventListener("click", closeNodeModal);

  var deleteNodeBtn = $("#deleteNodeButton");
  if (deleteNodeBtn)
    deleteNodeBtn.addEventListener("click", function () {
      if (state.editingNode && isValidNodeId(state.editingNode.id)) deleteNode(state.editingNode.id);
      else warnInvalidIdentifier("node");
    });

  var nodeEnabled = $("#nodeEnabled");
  if (nodeEnabled) nodeEnabled.addEventListener("change", updateStatusPreview);

  var checkNodeStatus = $("#checkNodeStatus");
  if (checkNodeStatus) checkNodeStatus.addEventListener("click", checkFormNode);

  var generateApiKeyBtn = $("#generateApiKey");
  if (generateApiKeyBtn) {
    generateApiKeyBtn.addEventListener("click", async function () {
      generateApiKeyBtn.disabled = true;
      try {
        var data = await api("/api/nodes/api-key", { method: "POST" });
        var apiKeyEl = $("#apiKey");
        if (apiKeyEl && data.api_key) apiKeyEl.value = data.api_key;
        showToast("New API key generated.", "success");
      } catch (err) {
        showToast(err.message || "Failed to generate API key.", "error");
      } finally {
        generateApiKeyBtn.disabled = false;
      }
    });
  }

  var nodeForm = $("#nodeForm");
  if (nodeForm) nodeForm.addEventListener("submit", saveNode);

  // --- Cores ---
  var createCoreBtn = $("#createCoreBtn");
  if (createCoreBtn)
    createCoreBtn.addEventListener("click", function () {
      openCoreCreateModal();
    });

  var coresEmptyCreate = $("#coresEmptyCreateBtn");
  if (coresEmptyCreate)
    coresEmptyCreate.addEventListener("click", function () {
      openCoreCreateModal();
    });

  var coreCreateModal = $("#coreCreateModal");
  if (coreCreateModal) {
    coreCreateModal.addEventListener("click", function (e) {
      if (e.target === coreCreateModal) closeCoreCreateModal();
    });
  }

  var closeCoreCreateModalBtn = $("#closeCoreCreateModal");
  if (closeCoreCreateModalBtn)
    closeCoreCreateModalBtn.addEventListener("click", closeCoreCreateModal);

  var cancelCoreCreateBtn = $("#cancelCoreCreateButton");
  if (cancelCoreCreateBtn)
    cancelCoreCreateBtn.addEventListener("click", closeCoreCreateModal);

  var coreCreateForm = $("#coreCreateForm");
  if (coreCreateForm) coreCreateForm.addEventListener("submit", createCore);

  // --- Core Editor navigation ---
  $$("#backToCoresBtn, #backToCoresBtn2, #backToCoresLink").forEach(
    function (el) {
      el.addEventListener("click", function () {
        switchPage("cores");
      });
    },
  );

  $$("#saveCoreBtn, #saveCoreEditorBottom").forEach(function (el) {
    el.addEventListener("click", saveCoreEditor);
  });
  $$("#applyCoreBtn, #applyCoreEditorBottom").forEach(function (el) {
    el.addEventListener("click", saveAndApplyCoreEditor);
  });

  // --- Core Editor tabs ---
  $$(".tab-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      switchCoreTab(btn.dataset.coreTab || btn.dataset.tab);
    });
  });

  // --- Core Editor add buttons ---
  var addInboundBtn = $("#addInboundButton");
  if (addInboundBtn) {
    addInboundBtn.addEventListener("click", function () {
      if (state.editorDraft) {
        state.editorDraft.inbounds.push(defaultInbound());
        renderCoreEditor();
        switchCoreTab("inbounds");
      }
    });
  }

  var addBalancerBtn = $("#addBalancerButton");
  if (addBalancerBtn) {
    addBalancerBtn.addEventListener("click", function () {
      if (state.editorDraft) {
        state.editorDraft.balancers.push(defaultBalancer());
        renderCoreEditor();
        switchCoreTab("balancers");
      }
    });
  }

  var addDependencyBtn = $("#addDependencyButton");
  if (addDependencyBtn) {
    addDependencyBtn.addEventListener("click", function () {
      if (state.editorDraft) {
        state.editorDraft.dependencies.push(defaultDependency());
        renderDependencyEditor();
      }
    });
  }

  // --- Core Editor header sync ---
  var editorCoreName = $("#editorCoreName");
  if (editorCoreName)
    editorCoreName.addEventListener("input", syncEditorHeaderToDraft);

  var editorCoreNode = $("#editorCoreNode");
  if (editorCoreNode)
    editorCoreNode.addEventListener("change", syncEditorHeaderToDraft);

  var editorCoreEnabled = $("#editorCoreEnabled");
  if (editorCoreEnabled)
    editorCoreEnabled.addEventListener("change", syncEditorHeaderToDraft);

  // --- Advanced JSON ---
  var advancedJsonEnabled = $("#advancedJsonEnabled");
  if (advancedJsonEnabled) advancedJsonEnabled.addEventListener("change", syncAdvancedEditorToDraft);

  var advancedJsonEditor = $("#advancedJsonEditor");
  if (advancedJsonEditor) advancedJsonEditor.addEventListener("input", syncAdvancedEditorToDraft);

  var validateAdvancedJsonButton = $("#validateAdvancedJsonButton");
  if (validateAdvancedJsonButton) validateAdvancedJsonButton.addEventListener("click", function () { validateAdvancedConfig(); });

  // --- Logs ---
  var refreshLogsBtn = $("#refreshLogsBtn");
  if (refreshLogsBtn) refreshLogsBtn.addEventListener("click", loadLogs);

  var logSourceSelect = $("#logSourceSelect");
  if (logSourceSelect) logSourceSelect.addEventListener("change", loadLogs);

  var logLimitSelect = $("#logLimitSelect");
  if (logLimitSelect) logLimitSelect.addEventListener("change", loadLogs);

  var logLevelSelect = $("#logLevelSelect");
  if (logLevelSelect) logLevelSelect.addEventListener("change", loadLogs);

  var logSearchInput = $("#logSearchInput");
  if (logSearchInput) {
    logSearchInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") loadLogs();
    });
  }

  var logRefreshIntervalInput = $("#logRefreshIntervalInput");
  if (logRefreshIntervalInput) {
    try {
      var savedInterval = localStorage.getItem("doctorDev.logRefreshIntervalSeconds");
      if (savedInterval) logRefreshIntervalInput.value = String(clampLogRefreshInterval(savedInterval));
    } catch (_) {}
    state.logRefreshIntervalSeconds = clampLogRefreshInterval(logRefreshIntervalInput.value);
    logRefreshIntervalInput.addEventListener("change", syncLogAutoRefresh);
    logRefreshIntervalInput.addEventListener("input", function () {
      state.logRefreshIntervalSeconds = clampLogRefreshInterval(logRefreshIntervalInput.value);
    });
  }

  var logAutoRefresh = $("#logAutoRefresh");
  if (logAutoRefresh) {
    logAutoRefresh.addEventListener("change", function () {
      if (logAutoRefresh.checked) {
        loadLogs({ silent: true });
        startLogAutoRefresh();
      } else {
        stopLogAutoRefresh(false);
      }
    });
  }

  var copyLogsBtn = $("#copyLogsBtn");
  if (copyLogsBtn) {
    copyLogsBtn.addEventListener("click", async function () {
      try {
        await navigator.clipboard.writeText(state.rawLogLines.join("\n"));
        showToast("Logs copied to clipboard.", "success");
      } catch (_) {
        showToast("Failed to copy logs.", "error");
      }
    });
  }

  var clearLogsBtn = $("#clearLogsBtn");
  if (clearLogsBtn) {
    clearLogsBtn.addEventListener("click", function () {
      var output = $("#logsOutput");
      if (output) output.innerHTML = "";
      state.rawLogLines = [];
      var lc = $("#logsLineCount");
      if (lc) lc.textContent = "0 lines";
    });
  }

  // --- Sidebar (mobile) ---
  var openSidebarBtn = $("#openSidebarBtn");
  var sidebar = $("#sidebar");
  var sidebarOverlay = $("#sidebarOverlay");
  var closeSidebarBtn = $("#closeSidebarBtn");

  if (openSidebarBtn && sidebar && sidebarOverlay) {
    openSidebarBtn.addEventListener("click", function () {
      sidebar.classList.add("open");
      sidebarOverlay.classList.remove("hidden");
    });
  }

  function closeSidebar() {
    if (sidebar) sidebar.classList.remove("open");
    if (sidebarOverlay) sidebarOverlay.classList.add("hidden");
  }

  if (closeSidebarBtn) closeSidebarBtn.addEventListener("click", closeSidebar);
  if (sidebarOverlay) sidebarOverlay.addEventListener("click", closeSidebar);

  // --- Global error handlers ---
  window.addEventListener("error", function (e) {
    console.error("Global error:", e.error || e.message);
  });
  window.addEventListener("unhandledrejection", function (e) {
    console.error("Unhandled rejection:", e.reason);
  });
});

// ============================================================
// 16. INIT
// ============================================================

checkSession();

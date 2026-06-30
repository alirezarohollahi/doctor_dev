/* ============================================================
   Doctor Dev Panel — Complete Application
   ============================================================ */
(function(){
'use strict';

/* ------------------------------------------------------------
   SVG ICONS
   ------------------------------------------------------------ */
const IC = {
    logo: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4m0 14v4M4.22 4.22l2.83 2.83m9.9 9.9l2.83 2.83M1 12h4m14 0h4M4.22 19.78l2.83-2.83m9.9-9.9l2.83-2.83"/></svg>',
    dashboard: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
    nodes: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></svg>',
    cores: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="5" r="3"/><circle cx="5" cy="19" r="3"/><circle cx="19" cy="19" r="3"/><line x1="12" y1="8" x2="5" y2="16"/><line x1="12" y1="8" x2="19" y2="16"/></svg>',
    logs: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/><line x1="8" y1="9" x2="10" y2="9"/></svg>',
    diag: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
    plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
    x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>',
    edit: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>',
    check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>',
    refresh: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>',
    eye: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>',
    upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>',
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>',
    key: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>',
    sync: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>',
    wrench: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>',
    alert: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>',
    chevDown: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><polyline points="6 9 12 15 18 9"/></svg>',
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>',
    logout: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
};

/* ------------------------------------------------------------
   STATE
   ------------------------------------------------------------ */
const S = {
    user: null,
    route: 'dashboard',
    nodes: [],
    cores: [],
    inboundCatalog: {},
    runtimeCache: {},
    summary: null,
    stats: null,
    integrity: null,
    logsSources: [],
    logsEntries: [],
    logsFilter: { source: 'panel', limit: 300, level: 'all', q: '' },
    loading: false,
    globalLoading: false,
    nodeEditor: { open: false, node: null, isNew: false },
    coreEditor: { open: false, core: null, inbounds: [], balancers: [], dependencies: [], advanced: { enabled: false, json_config: '' }, activeTab: 'overview', isNew: false },
    slidePanel: null, // { type, title, content }
    inboundSubEditor: null, // { index, data } or { index: -1, data: defaultInbound }
    balancerSubEditor: null, // { balIdx, epIdx, data }
    depSubEditor: null, // { index, data }
    nodeInboundSubEditor: null,
};

/* ------------------------------------------------------------
   UTILITY FUNCTIONS
   ------------------------------------------------------------ */
function esc(s) { if (s == null) return ''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function uid() { return 'dep_' + Math.random().toString(36).slice(2,10); }
function fmtTime(ts) { if (!ts) return '—'; try { const d = new Date(ts); if (isNaN(d)) return '—'; return d.toLocaleString(); } catch(e) { return '—'; } }
function fmtRel(ts) { if (!ts) return '—'; const s = Math.floor((Date.now() - new Date(ts).getTime())/1000); if (s < 60) return s+'s ago'; if (s < 3600) return Math.floor(s/60)+'m ago'; if (s < 86400) return Math.floor(s/3600)+'h ago'; return Math.floor(s/86400)+'d ago'; }
function fmtBytes(b) { if (b == null) return '—'; if (b < 1024) return b+'B'; if (b < 1048576) return (b/1024).toFixed(1)+'KB'; if (b < 1073741824) return (b/1048576).toFixed(1)+'MB'; return (b/1073741824).toFixed(2)+'GB'; }
function parsePorts(s) { if (!s || !s.trim()) return []; return [...new Set(s.split(',').map(p => parseInt(p.trim(),10)).filter(p => !isNaN(p) && p >= 1 && p <= 65535))]; }
function portsToStr(arr) { if (!arr || !arr.length) return ''; return arr.slice().sort((a,b)=>a-b).join(', '); }
function nodeStatusBadge(st) {
    const m = { running:['success','Running'], pending:['warning','Pending'], error:['error','Error'], disabled:['muted','Disabled'] };
    const [c,l] = m[st] || ['muted', st || 'Unknown'];
    const pulse = st === 'running' ? ' pulse' : '';
    return `<span class="badge badge-${c}"><span class="badge-dot${pulse}"></span>${esc(l)}</span>`;
}
function runtimeBadge(rt) {
    if (!rt) return '<span class="badge badge-muted">No Data</span>';
    if (rt.runtime_ok) return '<span class="badge badge-success"><span class="badge-dot pulse"></span>Active</span>';
    return '<span class="badge badge-error">Inactive</span>';
}
function boolBadge(v) { return v ? '<span class="badge badge-success">Yes</span>' : '<span class="badge badge-muted">No</span>'; }
function defaultInbound() { return { name:'', bind_ip:'0.0.0.0', public_host:'', port_mode:'fixed', fixed_ports:[], random_count:1, public_ports_mode:'use_inbound_ports', public_fixed_ports:[], public_random_count:1, target_type:'static', target_host:'127.0.0.1', target_port:80, target_balancer:'', enabled:true, notes:'' }; }
function defaultBalancer() { return { alias:'', strategy:'round_robin', endpoints:[], enabled:true, notes:'' }; }
function defaultEndpoint() { return { type:'static', host:'127.0.0.1', port:80, dependency_id:'', node_id:'', core_id:'', inbound_name:'', weight:1, enabled:true, notes:'' }; }
function defaultDependency(i) { return { id:uid(), type:'node', name:'dep '+(i+1), ref_id:'', host:'', sync_interval:5, required:true, notes:'' }; }
function getNodeById(id) { return S.nodes.find(n => n.id === id); }
function getCoreById(id) { return S.cores.find(c => c.id === id); }
function getNodeRuntime(nodeId) { return S.runtimeCache[nodeId] || null; }
function getCatalogForNode(nodeId) { return S.inboundCatalog[nodeId] || []; }

/* ------------------------------------------------------------
   API CLIENT
   ------------------------------------------------------------ */
class ApiError extends Error { constructor(status, detail) { super(detail); this.status = status; this.detail = detail; } }

async function api(method, path, body) {
    const opts = { method, credentials: 'same-origin', headers: {} };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const res = await fetch(path, opts);
    if (!res.ok) {
        let detail;
        try { const j = await res.json(); detail = j.detail || j.message || JSON.stringify(j); } catch(e) { detail = `HTTP ${res.status}`; }
        throw new ApiError(res.status, detail);
    }
    if (res.status === 204) return null;
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('json')) return res.json();
    return res.text();
}

const API = {
    auth: {
        login: (u,p) => api('POST','/api/auth/login',{username:u,password:p}),
        logout: () => api('POST','/api/auth/logout'),
        me: () => api('GET','/api/auth/me'),
    },
    panel: {
        summary: () => api('GET','/api/panel/summary'),
        stats: () => api('GET','/api/panel/stats'),
        integrity: () => api('GET','/api/panel/integrity'),
        repair: () => api('POST','/api/panel/repair'),
    },
    nodes: {
        list: () => api('GET','/api/nodes'),
        create: (d) => api('POST','/api/nodes', d),
        update: (id,d) => api('PUT','/api/nodes/'+id, d),
        delete: (id) => api('DELETE','/api/nodes/'+id),
        genKey: () => api('POST','/api/nodes/api-key'),
        checkAll: () => api('POST','/api/nodes/check'),
        checkOne: (id) => api('POST','/api/nodes/'+id+'/check'),
        syncAll: () => api('POST','/api/nodes/sync-runtime'),
        syncOne: (id) => api('POST','/api/nodes/'+id+'/sync-runtime'),
        runtimeCache: () => api('GET','/api/nodes/runtime-cache'),
        runtime: (id,refresh) => api('GET','/api/nodes/'+id+'/runtime?refresh='+(refresh?'true':'false')),
        drift: (id,refresh) => api('GET','/api/nodes/'+id+'/drift?refresh='+(refresh?'true':'false')),
        inbounds: (id) => api('GET','/api/nodes/'+id+'/inbounds'),
        configPreview: (id) => api('GET','/api/nodes/'+id+'/config-preview'),
        applyConfig: (id) => api('POST','/api/nodes/'+id+'/apply-config'),
    },
    cores: {
        list: () => api('GET','/api/cores'),
        create: (d) => api('POST','/api/cores', d),
        update: (id,d) => api('PUT','/api/cores/'+id, d),
        delete: (id) => api('DELETE','/api/cores/'+id),
        preview: (id) => api('GET','/api/cores/'+id+'/preview'),
        apply: (id) => api('POST','/api/cores/'+id+'/apply'),
        validateAdv: (d) => api('POST','/api/cores/advanced/validate', d),
    },
    logs: {
        sources: () => api('GET','/api/logs/sources'),
        list: (params) => api('GET','/api/logs?'+new URLSearchParams(params).toString()),
    },
};

/* ------------------------------------------------------------
   TOAST
   ------------------------------------------------------------ */
function toast(msg, type='info') {
    const root = document.getElementById('toast-root');
    const icons = { success:IC.check, error:IC.x, warning:IC.alert, info:IC.eye };
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.innerHTML = `<span class="toast-icon">${icons[type]||icons.info}</span><span class="toast-msg">${esc(msg)}</span><button class="toast-close">${IC.x}</button>`;
    root.appendChild(el);
    el.querySelector('.toast-close').onclick = () => removeToast(el);
    setTimeout(() => removeToast(el), 5000);
}
function removeToast(el) { if (el.classList.contains('removing')) return; el.classList.add('removing'); setTimeout(() => el.remove(), 200); }

/* ------------------------------------------------------------
   CONFIRM DIALOG
   ------------------------------------------------------------ */
function showConfirm({ title, text, icon='danger', confirmText='Confirm', cancelText='Cancel', onConfirm }) {
    const root = document.getElementById('overlay-root');
    const iconSvg = icon === 'warning' ? IC.alert : IC.alert;
    const el = document.createElement('div');
    el.className = 'modal-overlay';
    el.innerHTML = `<div class="modal" style="width:420px"><div class="modal-body">
        <div class="confirm-body">
            <div class="confirm-icon ${icon}">${iconSvg}</div>
            <div class="confirm-title">${esc(title)}</div>
            <div class="confirm-text">${esc(text)}</div>
            <div class="confirm-actions">
                <button class="btn btn-outline" data-action="confirm-cancel">${esc(cancelText)}</button>
                <button class="btn btn-danger" data-action="confirm-ok">${esc(confirmText)}</button>
            </div>
        </div>
    </div></div>`;
    root.appendChild(el);
    el.querySelector('[data-action="confirm-cancel"]').onclick = () => el.remove();
    el.querySelector('[data-action="confirm-ok"]').onclick = () => { el.remove(); onConfirm(); };
    el.onclick = (e) => { if (e.target === el) el.remove(); };
}

/* ------------------------------------------------------------
   MODAL HELPER
   ------------------------------------------------------------ */
function openModal(html, cls='') {
    const root = document.getElementById('overlay-root');
    const el = document.createElement('div');
    el.className = 'modal-overlay';
    el.innerHTML = `<div class="modal ${cls}">${html}</div>`;
    root.appendChild(el);
    el.onclick = (e) => { if (e.target === el) closeModal(el); };
    return el;
}
function closeModal(el) { if (el) el.remove(); }
function closeAllModals() { document.getElementById('overlay-root').innerHTML = ''; }

/* ------------------------------------------------------------
   SLIDE PANEL
   ------------------------------------------------------------ */
function openSlide(title, contentHtml, wide) {
    S.slidePanel = { title, contentHtml };
    renderOverlay();
}
function closeSlide() { S.slidePanel = null; renderOverlay(); }

/* ------------------------------------------------------------
   RENDER: OVERLAY ROOT (modals + slide panels)
   ------------------------------------------------------------ */
function renderOverlay() {
    const root = document.getElementById('overlay-root');
    let html = '';
    // Node editor modal
    if (S.nodeEditor.open) html += renderNodeEditorModal();
    // Core editor full panel
    if (S.coreEditor.open) html += renderCoreEditorPanel();
    // Slide panel
    if (S.slidePanel) html += renderSlidePanel();
    root.innerHTML = html;
    bindOverlayEvents();
}

/* ------------------------------------------------------------
   ROUTER
   ------------------------------------------------------------ */
function navigate(route) {
    S.route = route;
    S.inboundSubEditor = null;
    S.balancerSubEditor = null;
    S.depSubEditor = null;
    renderApp();
}

/* ------------------------------------------------------------
   MAIN RENDER
   ------------------------------------------------------------ */
function renderApp() {
    const app = document.getElementById('app');
    if (!S.user) { app.innerHTML = renderLogin(); bindLoginEvents(); return; }
    app.innerHTML = renderShell();
    bindShellEvents();
    renderPageContent();
}

function renderPageContent() {
    const content = document.getElementById('page-content');
    if (!content) return;
    switch(S.route) {
        case 'dashboard': content.innerHTML = renderDashboard(); bindDashboardEvents(); break;
        case 'nodes': content.innerHTML = renderNodes(); bindNodesEvents(); break;
        case 'cores': content.innerHTML = renderCores(); bindCoresEvents(); break;
        case 'logs': content.innerHTML = renderLogs(); bindLogsEvents(); break;
        case 'diagnostics': content.innerHTML = renderDiagnostics(); bindDiagnosticsEvents(); break;
        default: content.innerHTML = renderDashboard(); bindDashboardEvents();
    }
}

/* ------------------------------------------------------------
   LOGIN PAGE
   ------------------------------------------------------------ */
function renderLogin() {
    return `<div class="login-page">
        <div class="login-card">
            <div class="login-brand">${IC.logo}<h1>Doctor Dev</h1><p>Runtime Orchestration Panel</p></div>
            <div class="login-error" id="login-error"></div>
            <div class="login-field"><label>Username</label><input type="text" id="login-user" autocomplete="username" maxlength="80"></div>
            <div class="login-field"><label>Password</label><input type="password" id="login-pass" autocomplete="current-password" maxlength="256"></div>
            <button class="login-btn" id="login-btn">Sign In</button>
        </div>
    </div>`;
}
function bindLoginEvents() {
    const btn = document.getElementById('login-btn');
    const errEl = document.getElementById('login-error');
    const userEl = document.getElementById('login-user');
    const passEl = document.getElementById('login-pass');
    const doLogin = async () => {
        const u = userEl.value.trim(), p = passEl.value;
        if (!u || !p) { errEl.textContent = 'Username and password are required.'; errEl.classList.add('visible'); return; }
        errEl.classList.remove('visible');
        btn.disabled = true; btn.textContent = 'Signing in...';
        try {
            await API.auth.login(u, p);
            S.user = await API.auth.me();
            navigate('dashboard');
            await loadDashboardData();
            renderPageContent();
        } catch(e) {
            errEl.textContent = e.detail || 'Login failed';
            errEl.classList.add('visible');
            btn.disabled = false; btn.textContent = 'Sign In';
        }
    };
    btn.onclick = doLogin;
    passEl.onkeydown = (e) => { if (e.key === 'Enter') doLogin(); };
    userEl.focus();
}

/* ------------------------------------------------------------
   APP SHELL
   ------------------------------------------------------------ */
function renderShell() {
    const navItems = [
        { id:'dashboard', icon:IC.dashboard, label:'Dashboard' },
        { id:'nodes', icon:IC.nodes, label:'Nodes' },
        { id:'cores', icon:IC.cores, label:'Cores / Routing' },
        { id:'logs', icon:IC.logs, label:'Logs' },
        { id:'diagnostics', icon:IC.diag, label:'Diagnostics' },
    ];
    const initials = (S.user?.username || 'A').slice(0,2).toUpperCase();
    return `<div class="app-shell">
        <aside class="app-sidebar">
            <div class="sidebar-brand">${IC.logo}<span>Doctor Dev</span></div>
            <nav class="sidebar-nav">
                <div class="sidebar-section-label">Navigation</div>
                ${navItems.map(n => `<div class="sidebar-item${S.route===n.id?' active':''}" data-nav="${n.id}">${n.icon}<span>${n.label}</span></div>`).join('')}
            </nav>
            <div class="sidebar-footer">
                <div class="sidebar-user">
                    <div class="sidebar-user-avatar">${esc(initials)}</div>
                    <div class="sidebar-user-info"><div class="sidebar-user-name">${esc(S.user?.username||'')}</div><div class="sidebar-user-role">Administrator</div></div>
                    <button class="sidebar-logout" data-action="logout" title="Sign out">${IC.logout}</button>
                </div>
            </div>
        </aside>
        <header class="app-header">
            <div class="header-left">
                <span class="header-title">${esc({dashboard:'Dashboard',nodes:'Nodes',cores:'Cores / Routing',logs:'Logs',diagnostics:'Diagnostics'}[S.route]||'')}</span>
                ${S.globalLoading ? '<div class="spinner spinner-sm"></div>' : ''}
            </div>
            <div class="header-right">
                <button class="header-btn" data-action="global-refresh">${IC.refresh}<span>Refresh</span></button>
            </div>
        </header>
        <main class="app-content" id="page-content"></main>
    </div>`;
}
function bindShellEvents() {
    document.querySelectorAll('[data-nav]').forEach(el => {
        el.onclick = () => navigate(el.dataset.nav);
    });
    document.querySelector('[data-action="logout"]')?.addEventListener('click', async () => {
        try { await API.auth.logout(); } catch(e) {}
        S.user = null; S.nodes = []; S.cores = []; S.runtimeCache = {};
        renderApp();
    });
    document.querySelector('[data-action="global-refresh"]')?.addEventListener('click', async () => {
        S.globalLoading = true;
        const hdr = document.querySelector('.header-left');
        if (hdr) hdr.innerHTML = `<span class="header-title">${esc({dashboard:'Dashboard',nodes:'Nodes',cores:'Cores / Routing',logs:'Logs',diagnostics:'Diagnostics'}[S.route]||'')}</span><div class="spinner spinner-sm"></div>`;
        await loadDashboardData();
        S.globalLoading = false;
        renderApp();
        toast('Data refreshed', 'success');
    });
}

/* ------------------------------------------------------------
   DATA LOADING
   ------------------------------------------------------------ */
async function loadDashboardData() {
    try { S.nodes = await API.nodes.list(); } catch(e) { S.nodes = []; }
    try { const cr = await API.cores.list(); S.cores = cr.cores || cr || []; S.inboundCatalog = cr.inbound_catalog || {}; } catch(e) { S.cores = []; S.inboundCatalog = {}; }
    try { S.runtimeCache = await API.nodes.runtimeCache(); } catch(e) { S.runtimeCache = {}; }
    try { S.summary = await API.panel.summary(); } catch(e) { S.summary = null; }
    try { S.stats = await API.panel.stats(); } catch(e) { S.stats = null; }
}
async function loadIntegrity() { try { S.integrity = await API.panel.integrity(); } catch(e) { S.integrity = null; } }
async function loadLogsSources() { try { S.logsSources = await API.logs.sources(); } catch(e) { S.logsSources = []; } }
async function loadLogs() {
    try {
        const p = { source: S.logsFilter.source, limit: S.logsFilter.limit, level: S.logsFilter.level };
        if (S.logsFilter.q) p.q = S.logsFilter.q;
        S.logsEntries = await API.logs.list(p);
    } catch(e) { S.logsEntries = []; toast('Failed to load logs: ' + (e.detail||e.message), 'error'); }
}

/* ------------------------------------------------------------
   DASHBOARD PAGE
   ------------------------------------------------------------ */
function renderDashboard() {
    const nodes = S.nodes || [];
    const cores = S.cores || [];
    const rc = S.runtimeCache || {};
    const enabledNodes = nodes.filter(n => n.enabled);
    const runningNodes = nodes.filter(n => n.status === 'running');
    const errorNodes = nodes.filter(n => n.status === 'error');
    const pendingNodes = nodes.filter(n => n.status === 'pending');
    const disabledNodes = nodes.filter(n => !n.enabled);
    const enabledCores = cores.filter(c => c.enabled);
    const disabledCores = cores.filter(c => !c.enabled);
    let totalInbounds = 0, enabledInbounds = 0, totalBalancers = 0;
    cores.forEach(c => {
        const inbs = c.inbounds || [];
        totalInbounds += inbs.length;
        enabledInbounds += inbs.filter(i => i.enabled).length;
        totalBalancers += (c.balancers || []).length;
    });
    const nodesWithErrors = nodes.filter(n => n.last_error);
    const rtErrors = nodes.filter(n => { const r = rc[n.id]; return r && r.last_error; });
    const syncOk = nodes.length > 0 && nodes.every(n => { const r = rc[n.id]; return r && r.runtime_ok; });

    return `
    <div class="stats-grid">
        <div class="stat-card accent"><div class="stat-value">${nodes.length}</div><div class="stat-label">Total Nodes</div></div>
        <div class="stat-card accent"><div class="stat-value">${enabledNodes.length}</div><div class="stat-label">Enabled Nodes</div></div>
        <div class="stat-card info"><div class="stat-value">${runningNodes.length}</div><div class="stat-label">Running</div></div>
        <div class="stat-card error"><div class="stat-value">${errorNodes.length}</div><div class="stat-label">Error Nodes</div></div>
        <div class="stat-card warning"><div class="stat-value">${pendingNodes.length}</div><div class="stat-label">Pending</div></div>
        <div class="stat-card muted"><div class="stat-value">${disabledNodes.length}</div><div class="stat-label">Disabled</div></div>
        <div class="stat-card info"><div class="stat-value">${cores.length}</div><div class="stat-label">Total Cores</div></div>
        <div class="stat-card accent"><div class="stat-value">${enabledCores.length}</div><div class="stat-label">Enabled Cores</div></div>
        <div class="stat-card muted"><div class="stat-value">${disabledCores.length}</div><div class="stat-label">Disabled Cores</div></div>
        <div class="stat-card accent"><div class="stat-value">${enabledInbounds}</div><div class="stat-label">Enabled Inbounds</div></div>
        <div class="stat-card info"><div class="stat-value">${totalInbounds}</div><div class="stat-label">Total Inbounds</div></div>
        <div class="stat-card warning"><div class="stat-value">${totalBalancers}</div><div class="stat-label">Balancers</div></div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px">
        <div class="card">
            <div class="card-header"><h3>Runtime Health</h3>${syncOk ? '<span class="badge badge-success">Synced</span>' : '<span class="badge badge-warning">Drift Detected</span>'}</div>
            <div class="card-body compact">
                <div style="display:flex;justify-content:space-between;padding:4px 0;font-size:0.82rem"><span class="text-secondary">Nodes with runtime data</span><span>${Object.keys(rc).length} / ${nodes.length}</span></div>
                <div style="display:flex;justify-content:space-between;padding:4px 0;font-size:0.82rem"><span class="text-secondary">Runtime active</span><span class="text-accent">${nodes.filter(n=>rc[n.id]?.runtime_ok).length}</span></div>
                <div style="display:flex;justify-content:space-between;padding:4px 0;font-size:0.82rem"><span class="text-secondary">Config errors</span><span class="text-error">${nodesWithErrors.length}</span></div>
                <div style="display:flex;justify-content:space-between;padding:4px 0;font-size:0.82rem"><span class="text-secondary">Runtime errors</span><span class="text-error">${rtErrors.length}</span></div>
            </div>
        </div>
        <div class="card">
            <div class="card-header"><h3>Quick Actions</h3></div>
            <div class="card-body compact">
                <div class="quick-actions">
                    <button class="quick-action" data-action="add-node">${IC.plus} Add Node</button>
                    <button class="quick-action" data-action="add-core">${IC.plus} Add Core</button>
                    <button class="quick-action" data-action="view-logs">${IC.logs} View Logs</button>
                    <button class="quick-action" data-action="sync-runtime">${IC.sync} Sync Runtime</button>
                    <button class="quick-action" data-action="repair-data">${IC.wrench} Repair Data</button>
                </div>
            </div>
        </div>
    </div>

    ${nodesWithErrors.length ? `<div class="card mb-16">
        <div class="card-header"><h3>Nodes with Errors</h3></div>
        <div class="card-body compact">
            ${nodesWithErrors.map(n => `<div style="display:flex;align-items:center;gap:10px;padding:6px 0;font-size:0.82rem">
                ${nodeStatusBadge(n.status)} <strong>${esc(n.name)}</strong> <span class="text-muted">${esc(n.address)}</span> <span class="text-error">${esc((n.last_error||'').slice(0,120))}</span>
            </div>`).join('')}
        </div>
    </div>` : ''}

    <div class="card">
        <div class="card-header"><h3>Recent Nodes</h3></div>
        ${nodes.length ? `<div class="table-wrap"><table>
            <thead><tr><th>Status</th><th>Name</th><th>Address</th><th>Port</th><th>Runtime</th><th>Listeners</th><th>Last Checked</th></tr></thead>
            <tbody>${nodes.slice(0,8).map(n => {
                const rt = rc[n.id];
                return `<tr>
                    <td>${nodeStatusBadge(n.status)}</td>
                    <td><strong>${esc(n.name)}</strong></td>
                    <td class="mono">${esc(n.address)}</td>
                    <td class="mono">${n.api_port||'—'}</td>
                    <td>${runtimeBadge(rt)}</td>
                    <td class="mono">${rt?.listeners?.length ?? '—'}</td>
                    <td class="text-muted text-sm">${fmtRel(n.last_checked_at)}</td>
                </tr>`;
            }).join('')}</tbody>
        </table></div>` : '<div class="card-body"><div class="empty-state"><p>No nodes configured yet. Add your first node to get started.</p><button class="btn btn-primary" data-action="add-node">${IC.plus} Add Node</button></div></div>'}
    </div>`;
}
function bindDashboardEvents() {
    document.querySelector('[data-action="add-node"]')?.addEventListener('click', () => openNodeEditor(null));
    document.querySelector('[data-action="add-core"]')?.addEventListener('click', () => openCoreEditor(null));
    document.querySelector('[data-action="view-logs"]')?.addEventListener('click', () => navigate('logs'));
    document.querySelector('[data-action="sync-runtime"]')?.addEventListener('click', async () => {
        try { await API.nodes.syncAll(); toast('Runtime sync initiated', 'success'); await loadDashboardData(); renderPageContent(); } catch(e) { toast(e.detail||'Sync failed','error'); }
    });
    document.querySelector('[data-action="repair-data"]')?.addEventListener('click', () => navigate('diagnostics'));
}

/* ------------------------------------------------------------
   NODES PAGE
   ------------------------------------------------------------ */
function renderNodes() {
    const nodes = S.nodes || [];
    const rc = S.runtimeCache || {};
    if (!nodes.length) return `<div class="card"><div class="card-body"><div class="empty-state">${IC.nodes}<h3>No Nodes Yet</h3><p>Nodes are the runtime instances that forward traffic. Add your first node to begin.</p><button class="btn btn-primary" data-action="add-node">${IC.plus} Add Node</button></div></div></div>`;
    return `<div style="display:flex;justify-content:flex-end;margin-bottom:14px"><button class="btn btn-primary" data-action="add-node">${IC.plus} Add Node</button></div>
    <div class="card"><div class="table-wrap"><table>
        <thead><tr><th>Status</th><th>Name</th><th>Address</th><th>Desired Port</th><th>Runtime Port</th><th>Enabled</th><th>Runtime</th><th>Listeners</th><th>Last Checked</th><th>Last Error</th><th>Actions</th></tr></thead>
        <tbody>${nodes.map(n => {
            const rt = rc[n.id];
            return `<tr>
                <td>${nodeStatusBadge(n.status)}</td>
                <td><strong>${esc(n.name)}</strong></td>
                <td class="mono">${esc(n.address)}</td>
                <td class="mono">${n.api_port}</td>
                <td class="mono">${rt?.api?.api_port ?? '—'}</td>
                <td>${boolBadge(n.enabled)}</td>
                <td>${runtimeBadge(rt)}</td>
                <td class="mono">${rt?.listeners?.length ?? '—'}</td>
                <td class="text-muted text-sm">${fmtRel(n.last_checked_at)}</td>
                <td class="text-xs" style="max-width:160px" title="${esc(n.last_error||'')}"><span class="text-error">${esc((n.last_error||'').slice(0,50))}</span></td>
                <td><div class="actions-cell">
                    <button class="btn btn-xs btn-ghost" data-action="edit-node" data-id="${n.id}" title="Edit">${IC.edit}</button>
                    <button class="btn btn-xs btn-ghost" data-action="check-node" data-id="${n.id}" title="Check">${IC.eye}</button>
                    <button class="btn btn-xs btn-ghost" data-action="sync-node" data-id="${n.id}" title="Sync">${IC.sync}</button>
                    <button class="btn btn-xs btn-ghost" data-action="node-runtime" data-id="${n.id}" title="Runtime">${IC.diag}</button>
                    <button class="btn btn-xs btn-ghost" data-action="node-drift" data-id="${n.id}" title="Drift">${IC.alert}</button>
                    <button class="btn btn-xs btn-ghost" data-action="node-preview" data-id="${n.id}" title="Config Preview">${IC.eye}</button>
                    <button class="btn btn-xs btn-ghost" data-action="node-apply" data-id="${n.id}" title="Apply Config">${IC.upload}</button>
                    <button class="btn btn-xs btn-ghost text-error" data-action="delete-node" data-id="${n.id}" title="Delete">${IC.trash}</button>
                </div></td>
            </tr>`;
        }).join('')}</tbody>
    </table></div></div>`;
}
function bindNodesEvents() {
    document.querySelector('[data-action="add-node"]')?.addEventListener('click', () => openNodeEditor(null));
    document.querySelectorAll('[data-action="edit-node"]').forEach(el => el.onclick = () => { const n = getNodeById(el.dataset.id); if(n) openNodeEditor(n); });
    document.querySelectorAll('[data-action="delete-node"]').forEach(el => el.onclick = () => {
        const n = getNodeById(el.dataset.id); if(!n) return;
        showConfirm({ title:'Delete Node', text:`This will permanently delete "${n.name}". Any cores linked to this node will be affected.`, confirmText:'Delete', onConfirm: async () => {
            try { await API.nodes.delete(n.id); toast('Node deleted','success'); await loadDashboardData(); renderPageContent(); } catch(e) { toast(e.detail||'Delete failed','error'); }
        }});
    });
    document.querySelectorAll('[data-action="check-node"]').forEach(el => el.onclick = async () => {
        const id = el.dataset.id; el.disabled = true;
        try { await API.nodes.checkOne(id); toast('Node check completed','success'); await loadDashboardData(); renderPageContent(); } catch(e) { toast(e.detail||'Check failed','error'); el.disabled = false; }
    });
    document.querySelectorAll('[data-action="sync-node"]').forEach(el => el.onclick = async () => {
        const id = el.dataset.id; el.disabled = true;
        try { await API.nodes.syncOne(id); toast('Runtime synced','success'); await loadDashboardData(); renderPageContent(); } catch(e) { toast(e.detail||'Sync failed','error'); el.disabled = false; }
    });
    document.querySelectorAll('[data-action="node-runtime"]').forEach(el => el.onclick = () => loadNodeRuntime(el.dataset.id));
    document.querySelectorAll('[data-action="node-drift"]').forEach(el => el.onclick = () => loadNodeDrift(el.dataset.id));
    document.querySelectorAll('[data-action="node-preview"]').forEach(el => el.onclick = () => loadNodePreview(el.dataset.id));
    document.querySelectorAll('[data-action="node-apply"]').forEach(el => el.onclick = () => {
        const n = getNodeById(el.dataset.id); if(!n) return;
        showConfirm({ title:'Apply Config to Node', text:`Push the current desired configuration to "${n.name}". This will update the node's running config.`, icon:'warning', confirmText:'Apply Config', onConfirm: async () => {
            try { await API.nodes.applyConfig(n.id); toast('Config applied','success'); await loadDashboardData(); renderPageContent(); } catch(e) { toast(e.detail||'Apply failed','error'); }
        }});
    });
}

/* ------------------------------------------------------------
   NODE EDITOR MODAL
   ------------------------------------------------------------ */
function openNodeEditor(node) {
    S.nodeEditor = { open: true, node: node ? {...node} : { name:'', address:'', api_port:62051, api_key:'', peer_token_refresh_interval:30, peer_token_ttl:120, enabled:true }, isNew: !node };
    renderOverlay();
}
function renderNodeEditorModal() {
    const ne = S.nodeEditor;
    const n = ne.node;
    return `<div class="modal-overlay"><div class="modal wide">
        <div class="modal-header"><h2>${ne.isNew ? 'Add Node' : 'Edit Node'}</h2><button class="modal-close" data-action="close-node-editor">${IC.x}</button></div>
        <div class="modal-body">
            <div class="form-row">
                <div class="form-group"><label class="form-label">Name<span class="required">*</span></label><input class="form-input" id="ne-name" value="${esc(n.name)}" maxlength="120"><div class="form-error" id="ne-name-err"></div></div>
                <div class="form-group"><label class="form-label">Address<span class="required">*</span></label><input class="form-input" id="ne-address" value="${esc(n.address)}" maxlength="255" placeholder="127.0.0.1 or hostname"><div class="form-error" id="ne-address-err"></div></div>
            </div>
            <div class="form-row-3">
                <div class="form-group"><label class="form-label">API Port<span class="required">*</span></label><input type="number" class="form-input" id="ne-port" value="${n.api_port}" min="1" max="65535"><div class="form-error" id="ne-port-err"></div></div>
                <div class="form-group"><label class="form-label">Peer Token Refresh (s)</label><input type="number" class="form-input" id="ne-ptri" value="${n.peer_token_refresh_interval}" min="5" max="86400"><div class="form-hint">How often dependents refresh tokens</div></div>
                <div class="form-group"><label class="form-label">Peer Token TTL (s)</label><input type="number" class="form-input" id="ne-pttl" value="${n.peer_token_ttl}" min="10" max="86400"><div class="form-hint">Backend normalizes to ≥ 2× refresh</div></div>
            </div>
            <div class="form-group">
                <label class="form-label">API Key<span class="required">*</span></label>
                <div style="display:flex;gap:8px"><input class="form-input" id="ne-apikey" value="${esc(n.api_key)}" maxlength="255" type="password" style="flex:1"><button class="btn btn-outline btn-sm" data-action="gen-apikey">${IC.key} Generate</button></div>
                <div class="form-error" id="ne-apikey-err"></div>
            </div>
            <div class="form-group">
                <label class="form-toggle"><input type="checkbox" id="ne-enabled" ${n.enabled?'checked':''}><span>Enabled</span></label>
            </div>
        </div>
        <div class="modal-footer">
            <button class="btn btn-outline" data-action="close-node-editor">Cancel</button>
            <button class="btn btn-primary" data-action="save-node">${ne.isNew ? 'Create Node' : 'Save Changes'}</button>
        </div>
    </div></div>`;
}
function bindOverlayEvents() {
    // Close node editor
    document.querySelectorAll('[data-action="close-node-editor"]').forEach(el => el.onclick = () => { S.nodeEditor.open = false; renderOverlay(); });
    // Generate API key
    document.querySelector('[data-action="gen-apikey"]')?.addEventListener('click', async () => {
        try { const r = await API.nodes.genKey(); document.getElementById('ne-apikey').value = r.api_key || r.key || r; toast('API key generated','success'); } catch(e) { toast(e.detail||'Failed','error'); }
    });
    // Save node
    document.querySelector('[data-action="save-node"]')?.addEventListener('click', saveNode);
    // Core editor close
    document.querySelectorAll('[data-action="close-core-editor"]').forEach(el => el.onclick = () => { S.coreEditor.open = false; renderOverlay(); });
    // Core editor tabs
    document.querySelectorAll('.fp-tab').forEach(el => el.onclick = () => { S.coreEditor.activeTab = el.dataset.tab; renderOverlay(); });
    // Core editor save
    document.querySelectorAll('[data-action="save-core"]').forEach(el => el.onclick = () => saveCore(false));
    document.querySelectorAll('[data-action="save-apply-core"]').forEach(el => el.onclick = () => saveCore(true));
    document.querySelectorAll('[data-action="delete-core"]').forEach(el => el.onclick = deleteCore);
    document.querySelectorAll('[data-action="preview-core"]').forEach(el => el.onclick = previewCore);
    document.querySelectorAll('[data-action="apply-core-now"]').forEach(el => el.onclick = applyCoreNow);
    // Inbound sub-editor
    document.querySelectorAll('[data-action="add-inbound"]').forEach(el => el.onclick = () => { S.inboundSubEditor = { index: -1, data: defaultInbound() }; renderOverlay(); });
    document.querySelectorAll('[data-action="edit-inbound"]').forEach(el => el.onclick = () => { const idx = parseInt(el.dataset.idx); S.inboundSubEditor = { index: idx, data: {...S.coreEditor.inbounds[idx]} }; renderOverlay(); });
    document.querySelectorAll('[data-action="delete-inbound"]').forEach(el => el.onclick = () => { const idx = parseInt(el.dataset.idx); S.coreEditor.inbounds.splice(idx,1); S.inboundSubEditor = null; renderOverlay(); });
    document.querySelectorAll('[data-action="cancel-inbound"]').forEach(el => el.onclick = () => { S.inboundSubEditor = null; renderOverlay(); });
    document.querySelectorAll('[data-action="save-inbound"]').forEach(el => el.onclick = saveInbound);
    // Balancer sub-editor
    document.querySelectorAll('[data-action="add-balancer"]').forEach(el => el.onclick = () => { S.coreEditor.balancers.push(defaultBalancer()); S.balancerSubEditor = { balIdx: S.coreEditor.balancers.length-1, epIdx: -1 }; renderOverlay(); });
    document.querySelectorAll('[data-action="edit-balancer"]').forEach(el => el.onclick = () => { S.balancerSubEditor = { balIdx: parseInt(el.dataset.idx), epIdx: -1 }; renderOverlay(); });
    document.querySelectorAll('[data-action="delete-balancer"]').forEach(el => el.onclick = () => { const idx = parseInt(el.dataset.idx); S.coreEditor.balancers.splice(idx,1); S.balancerSubEditor = null; renderOverlay(); });
    document.querySelectorAll('[data-action="cancel-balancer"]').forEach(el => el.onclick = () => { S.balancerSubEditor = null; renderOverlay(); });
    document.querySelectorAll('[data-action="save-balancer"]').forEach(el => el.onclick = saveBalancer);
    // Endpoint
    document.querySelectorAll('[data-action="add-endpoint"]').forEach(el => el.onclick = () => { const bi = parseInt(el.dataset.balidx); S.coreEditor.balancers[bi].endpoints.push(defaultEndpoint()); S.balancerSubEditor = { balIdx: bi, epIdx: S.coreEditor.balancers[bi].endpoints.length-1 }; renderOverlay(); });
    document.querySelectorAll('[data-action="edit-endpoint"]').forEach(el => el.onclick = () => { S.balancerSubEditor = { balIdx: parseInt(el.dataset.balidx), epIdx: parseInt(el.dataset.epidx) }; renderOverlay(); });
    document.querySelectorAll('[data-action="delete-endpoint"]').forEach(el => el.onclick = () => { const bi = parseInt(el.dataset.balidx), ei = parseInt(el.dataset.epidx); S.coreEditor.balancers[bi].endpoints.splice(ei,1); if(S.balancerSubEditor?.epIdx === ei) S.balancerSubEditor.epIdx = -1; renderOverlay(); });
    document.querySelectorAll('[data-action="save-endpoint"]').forEach(el => el.onclick = saveEndpoint);
    document.querySelectorAll('[data-action="cancel-endpoint"]').forEach(el => el.onclick = () => { S.balancerSubEditor = { ...S.balancerSubEditor, epIdx: -1 }; renderOverlay(); });
    // Dependency sub-editor
    document.querySelectorAll('[data-action="add-dep"]').forEach(el => el.onclick = () => { S.coreEditor.dependencies.push(defaultDependency(S.coreEditor.dependencies.length)); S.depSubEditor = { index: S.coreEditor.dependencies.length-1, data: null }; renderOverlay(); });
    document.querySelectorAll('[data-action="edit-dep"]').forEach(el => el.onclick = () => { S.depSubEditor = { index: parseInt(el.dataset.idx), data: null }; renderOverlay(); });
    document.querySelectorAll('[data-action="delete-dep"]').forEach(el => el.onclick = () => {
        const idx = parseInt(el.dataset.idx);
        const dep = S.coreEditor.dependencies[idx];
        // Check if used by endpoints
        const used = S.coreEditor.balancers.some(b => b.endpoints.some(ep => ep.dependency_id === dep?.id));
        const doDelete = async () => { S.coreEditor.dependencies.splice(idx,1); S.depSubEditor = null; renderOverlay(); };
        if (used) { showConfirm({ title:'Remove Dependency', text:'This dependency is used by one or more balancer endpoints. Removing it will leave those endpoints without a valid reference.', icon:'warning', confirmText:'Remove Anyway', onConfirm: doDelete }); }
        else doDelete();
    });
    document.querySelectorAll('[data-action="cancel-dep"]').forEach(el => el.onclick = () => { S.depSubEditor = null; renderOverlay(); });
    document.querySelectorAll('[data-action="save-dep"]').forEach(el => el.onclick = saveDependency);
    // Advanced JSON
    document.querySelectorAll('[data-action="validate-json-local"]').forEach(el => el.onclick = validateJsonLocal);
    document.querySelectorAll('[data-action="validate-json-backend"]').forEach(el => el.onclick = validateJsonBackend);
    // Slide panel close
    document.querySelectorAll('[data-action="close-slide"]').forEach(el => el.onclick = closeSlide);
    // Slide panel copy
    document.querySelectorAll('[data-action="copy-slide-content"]').forEach(el => el.onclick = () => {
        const pre = document.querySelector('#slide-json-content');
        if (pre) { navigator.clipboard.writeText(pre.textContent).then(() => toast('Copied','success')).catch(() => toast('Copy failed','error')); }
    });
    // Slide panel refresh
    document.querySelectorAll('[data-action="refresh-slide"]').forEach(el => el.onclick = () => {
        if (S.slidePanel?.onRefresh) S.slidePanel.onRefresh();
    });
    // Inbound port_mode / public_ports_mode / target_type changes
    document.querySelectorAll('[data-inbound-field="port_mode"]').forEach(el => el.onchange = () => renderOverlay());
    document.querySelectorAll('[data-inbound-field="public_ports_mode"]').forEach(el => el.onchange = () => renderOverlay());
    document.querySelectorAll('[data-inbound-field="target_type"]').forEach(el => el.onchange = () => renderOverlay());
    // Endpoint type change
    document.querySelectorAll('[data-ep-field="type"]').forEach(el => el.onchange = () => {
        const bi = S.balancerSubEditor?.balIdx, ei = S.balancerSubEditor?.epIdx;
        if (bi != null && ei != null && S.coreEditor.balancers[bi]?.endpoints[ei]) {
            const ep = S.coreEditor.balancers[bi].endpoints[ei];
            if (el.value === 'static') { ep.dependency_id=''; ep.node_id=''; ep.core_id=''; ep.inbound_name=''; }
            else { ep.host=''; ep.port=80; }
        }
        renderOverlay();
    });
    // Dependency node change
    document.querySelectorAll('[data-dep-field="ref_id"]').forEach(el => el.onchange = () => renderOverlay());
}

async function saveNode() {
    const name = document.getElementById('ne-name').value.trim();
    const address = document.getElementById('ne-address').value.trim();
    const api_port = parseInt(document.getElementById('ne-port').value);
    const api_key = document.getElementById('ne-apikey').value.trim();
    const ptri = parseInt(document.getElementById('ne-ptri').value);
    const pttl = parseInt(document.getElementById('ne-pttl').value);
    const enabled = document.getElementById('ne-enabled').checked;
    let valid = true;
    const showErr = (id, msg) => { const e = document.getElementById(id); if(e){e.textContent=msg;e.classList.add('visible');} valid=false; };
    const hideErr = (id) => { const e = document.getElementById(id); if(e){e.textContent='';e.classList.remove('visible');} };
    hideErr('ne-name-err'); hideErr('ne-address-err'); hideErr('ne-port-err'); hideErr('ne-apikey-err');
    if (!name || name.length < 1) showErr('ne-name-err','Name is required');
    else if (name.length > 120) showErr('ne-name-err','Max 120 characters');
    if (!address || address.length < 1) showErr('ne-address-err','Address is required');
    else if (address.length > 255) showErr('ne-address-err','Max 255 characters');
    if (isNaN(api_port) || api_port < 1 || api_port > 65535) showErr('ne-port-err','Port must be 1-65535');
    if (!api_key) showErr('ne-apikey-err','API key is required');
    if (!valid) return;
    const payload = { name, address, api_port, api_key, peer_token_refresh_interval: ptri||30, peer_token_ttl: pttl||120, enabled };
    try {
        if (S.nodeEditor.isNew) { await API.nodes.create(payload); toast('Node created','success'); }
        else { await API.nodes.update(S.nodeEditor.node.id, payload); toast('Node updated','success'); }
        S.nodeEditor.open = false;
        await loadDashboardData();
        renderOverlay();
        renderPageContent();
    } catch(e) { toast(e.detail || 'Save failed', 'error'); }
}

/* ------------------------------------------------------------
   NODE RUNTIME / DRIFT / PREVIEW (Slide Panels)
   ------------------------------------------------------------ */
async function loadNodeRuntime(nodeId) {
    const n = getNodeById(nodeId); if(!n) return;
    openSlide('Runtime: ' + n.name, '<div style="text-align:center;padding:40px"><div class="spinner"></div></div>');
    try {
        const rt = await API.nodes.runtime(nodeId, true);
        S.slidePanel.contentHtml = renderRuntimeContent(n, rt);
        S.slidePanel.onRefresh = () => loadNodeRuntime(nodeId);
        renderOverlay();
    } catch(e) { S.slidePanel.contentHtml = `<div class="inline-warning">${IC.alert} <span>${esc(e.detail || 'Failed to load runtime')}</span></div>`; renderOverlay(); }
}
function renderRuntimeContent(node, rt) {
    if (!rt) return '<div class="empty-state"><p>No runtime data available.</p></div>';
    const rows = [
        ['Runtime OK', boolBadge(rt.runtime_ok)],
        ['Auth OK', boolBadge(rt.auth_ok)],
        ['Reachable', boolBadge(rt.reachable)],
        ['Generated At', fmtTime(rt.generated_at)],
        ['Exported At', fmtTime(rt.exported_at)],
        ['Config Hash', rt.config_hash ? `<span class="mono text-xs">${esc(rt.config_hash)}</span>` : '—'],
        ['API Host', esc(rt.api?.host || '—')],
        ['API Port', rt.api?.api_port || '—'],
        ['API Config Port', rt.api?.port || '—'],
        ['Active Connections', rt.active_connections ?? '—'],
        ['Connection Count', rt.connection_count ?? '—'],
        ['Bytes In', fmtBytes(rt.bytes_in)],
        ['Bytes Out', fmtBytes(rt.bytes_out)],
        ['Last Error', rt.last_error ? `<span class="text-error">${esc(rt.last_error)}</span>` : '—'],
    ];
    if (rt.core) {
        rows.push(['Core Name', esc(rt.core.name || '—')]);
        rows.push(['Core Enabled', boolBadge(rt.core.enabled)]);
    }
    if (rt.peer_sync_errors) rows.push(['Peer Sync Errors', rt.peer_sync_errors]);
    if (rt.peer_sync_cache_nodes != null) rows.push(['Peer Sync Cache Nodes', rt.peer_sync_cache_nodes]);
    if (rt.peer_sync_last) rows.push(['Peer Sync Last', fmtTime(rt.peer_sync_last)]);
    let html = '<div style="display:grid;gap:2px;margin-bottom:20px">';
    rows.forEach(([k,v]) => { html += `<div style="display:flex;justify-content:space-between;padding:8px 12px;background:var(--bg-deep);font-size:0.82rem"><span class="text-secondary">${k}</span><span>${v}</span></div>`; });
    html += '</div>';
    if (rt.listeners?.length) {
        html += '<h4 style="font-size:0.85rem;font-weight:700;margin-bottom:8px">Listeners</h4>';
        rt.listeners.forEach(l => {
            html += `<div style="background:var(--bg-deep);padding:8px 12px;margin-bottom:4px;font-size:0.8rem;font-family:var(--font-mono);border-radius:var(--radius-xs)">${esc(l.bind_ip||'*')}:${esc(l.port||'')} → ${esc(l.target_host||'')}:${esc(l.target_port||'')}</div>`;
        });
    }
    if (rt.advertised_inbounds?.length) {
        html += '<h4 style="font-size:0.85rem;font-weight:700;margin:16px 0 8px">Advertised Inbounds</h4>';
        rt.advertised_inbounds.forEach(ai => {
            html += `<div style="background:var(--bg-deep);padding:8px 12px;margin-bottom:4px;font-size:0.8rem;font-family:var(--font-mono);border-radius:var(--radius-xs)">${esc(ai.name||'')} — ${esc(ai.public_host||'')}:${esc(ai.public_ports?.join(', ')||'')}</div>`;
        });
    }
    return html;
}

async function loadNodeDrift(nodeId) {
    const n = getNodeById(nodeId); if(!n) return;
    openSlide('Drift: ' + n.name, '<div style="text-align:center;padding:40px"><div class="spinner"></div></div>');
    try {
        const d = await API.nodes.drift(nodeId, true);
        S.slidePanel.contentHtml = renderDriftContent(d);
        S.slidePanel.onRefresh = () => loadNodeDrift(nodeId);
        renderOverlay();
    } catch(e) { S.slidePanel.contentHtml = `<div class="inline-warning">${IC.alert} <span>${esc(e.detail || 'Failed to load drift')}</span></div>`; renderOverlay(); }
}
function renderDriftContent(d) {
    if (!d) return '<div class="empty-state"><p>No drift data available.</p></div>';
    let html = `<div style="margin-bottom:16px">${nodeStatusBadge(d.status || 'unknown')}</div>`;
    html += `<div style="font-size:0.82rem;margin-bottom:16px"><span class="text-secondary">Last Sync:</span> ${fmtTime(d.last_sync)}</div>`;
    if (d.desired_inbounds?.length) {
        html += '<div class="drift-section"><h4>Desired Inbounds</h4>';
        d.desired_inbounds.forEach(i => { html += `<div class="drift-item ok">${IC.check} ${esc(i.name||'')} ${esc(i.bind_ip||'')}:${esc((i.fixed_ports||[]).join(','))}</div>`; });
        html += '</div>';
    }
    if (d.runtime_listeners?.length) {
        html += '<div class="drift-section"><h4>Runtime Listeners</h4>';
        d.runtime_listeners.forEach(l => { html += `<div class="drift-item ok">${IC.check} ${esc(l.bind_ip||'*')}:${esc(l.port||'')}</div>`; });
        html += '</div>';
    }
    if (d.missing_listeners?.length) {
        html += '<div class="drift-section"><h4 class="text-error">Missing Listeners</h4>';
        d.missing_listeners.forEach(m => { html += `<div class="drift-item missing">${IC.x} ${esc(m)}</div>`; });
        html += '</div>';
    }
    if (d.extra_listeners?.length) {
        html += '<div class="drift-section"><h4 class="text-warning">Extra Listeners</h4>';
        d.extra_listeners.forEach(e => { html += `<div class="drift-item extra">${IC.alert} ${esc(e)}</div>`; });
        html += '</div>';
    }
    if (d.mismatch_messages?.length) {
        html += '<div class="drift-section"><h4 class="text-error">Mismatches</h4>';
        d.mismatch_messages.forEach(m => { html += `<div class="drift-item missing">${esc(m)}</div>`; });
        html += '</div>';
    }
    if (!d.missing_listeners?.length && !d.extra_listeners?.length && !d.mismatch_messages?.length) {
        html += '<div class="inline-info" style="margin-top:8px">' + IC.check + ' <span>No drift detected. Desired config matches runtime.</span></div>';
    }
    return html;
}

async function loadNodePreview(nodeId) {
    const n = getNodeById(nodeId); if(!n) return;
    openSlide('Config Preview: ' + n.name, '<div style="text-align:center;padding:40px"><div class="spinner"></div></div>');
    try {
        const data = await API.nodes.configPreview(nodeId);
        const json = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
        S.slidePanel.contentHtml = `<div class="code-block-header"><span>Configuration JSON</span><button class="copy-btn" data-action="copy-slide-content">${IC.copy} Copy</button></div><pre class="code-block" id="slide-json-content">${esc(json)}</pre>`;
        S.slidePanel.onRefresh = () => loadNodePreview(nodeId);
        renderOverlay();
    } catch(e) { S.slidePanel.contentHtml = `<div class="inline-warning">${IC.alert} <span>${esc(e.detail || 'Failed to load preview')}</span></div>`; renderOverlay(); }
}

function renderSlidePanel() {
    const sp = S.slidePanel;
    return `<div class="slide-overlay" data-action="close-slide"></div>
    <div class="slide-panel">
        <div class="slide-header">
            <h2>${esc(sp.title)}</h2>
            <div style="display:flex;gap:6px">
                ${sp.onRefresh ? `<button class="btn btn-xs btn-outline" data-action="refresh-slide">${IC.refresh}</button>` : ''}
                <button class="modal-close" data-action="close-slide">${IC.x}</button>
            </div>
        </div>
        <div class="slide-body">${sp.contentHtml}</div>
    </div>`;
}

/* ------------------------------------------------------------
   CORES PAGE
   ------------------------------------------------------------ */
function renderCores() {
    const cores = S.cores || [];
    if (!cores.length) return `<div class="card"><div class="card-body"><div class="empty-state">${IC.cores}<h3>No Cores Yet</h3><p>Cores define routing configurations for nodes. Create a core to configure inbounds and balancers.</p><button class="btn btn-primary" data-action="add-core">${IC.plus} Add Core</button></div></div></div>`;
    return `<div style="display:flex;justify-content:flex-end;margin-bottom:14px"><button class="btn btn-primary" data-action="add-core">${IC.plus} Add Core</button></div>
    <div class="card"><div class="table-wrap"><table>
        <thead><tr><th>Name</th><th>Node</th><th>Enabled</th><th>Inbounds</th><th>Balancers</th><th>Deps</th><th>Advanced</th><th>Actions</th></tr></thead>
        <tbody>${cores.map(c => {
            const n = getNodeById(c.node_id);
            const inbs = c.inbounds || [];
            const bals = c.balancers || [];
            const deps = c.dependencies || [];
            return `<tr>
                <td><strong>${esc(c.name)}</strong></td>
                <td>${n ? esc(n.name) : '<span class="text-error">Missing Node</span>'}</td>
                <td>${boolBadge(c.enabled)}</td>
                <td class="mono">${inbs.length} (${inbs.filter(i=>i.enabled).length} on)</td>
                <td class="mono">${bals.length} (${bals.filter(b=>b.enabled).length} on)</td>
                <td class="mono">${deps.length}</td>
                <td>${c.advanced?.enabled ? '<span class="badge badge-warning">On</span>' : '<span class="badge badge-muted">Off</span>'}</td>
                <td><div class="actions-cell">
                    <button class="btn btn-xs btn-primary" data-action="edit-core" data-id="${c.id}">${IC.edit} Edit</button>
                    <button class="btn btn-xs btn-ghost text-error" data-action="delete-core-inline" data-id="${c.id}">${IC.trash}</button>
                </div></td>
            </tr>`;
        }).join('')}</tbody>
    </table></div></div>`;
}
function bindCoresEvents() {
    document.querySelector('[data-action="add-core"]')?.addEventListener('click', () => openCoreEditor(null));
    document.querySelectorAll('[data-action="edit-core"]').forEach(el => el.onclick = () => { const c = getCoreById(el.dataset.id); if(c) openCoreEditor(c); });
    document.querySelectorAll('[data-action="delete-core-inline"]').forEach(el => el.onclick = () => {
        const c = getCoreById(el.dataset.id); if(!c) return;
        showConfirm({ title:'Delete Core', text:`This will permanently delete "${c.name}" and all its inbounds, balancers, and dependencies.`, confirmText:'Delete', onConfirm: async () => {
            try { await API.cores.delete(c.id); toast('Core deleted','success'); await loadDashboardData(); renderPageContent(); } catch(e) { toast(e.detail||'Delete failed','error'); }
        }});
    });
}

/* ------------------------------------------------------------
   CORE EDITOR (Full Panel)
   ------------------------------------------------------------ */
function openCoreEditor(core) {
    const isNew = !core;
    const c = core ? JSON.parse(JSON.stringify(core)) : { name:'', node_id:'', enabled:true };
    S.coreEditor = {
        open: true,
        core: c,
        inbounds: c.inbounds ? JSON.parse(JSON.stringify(c.inbounds)) : [],
        balancers: c.balancers ? JSON.parse(JSON.stringify(c.balancers)) : [],
        dependencies: c.dependencies ? JSON.parse(JSON.stringify(c.dependencies)) : [],
        advanced: c.advanced ? {...c.advanced} : { enabled: false, json_config: '' },
        activeTab: 'overview',
        isNew: isNew,
    };
    S.inboundSubEditor = null;
    S.balancerSubEditor = null;
    S.depSubEditor = null;
    renderOverlay();
}

function renderCoreEditorPanel() {
    const ce = S.coreEditor;
    const c = ce.core;
    const tabs = ['overview','inbounds','balancers','dependencies','advanced','preview'];
    const tabLabels = { overview:'Overview', inbounds:'Inbounds', balancers:'Balancers', dependencies:'Dependencies', advanced:'Advanced JSON', preview:'Preview / Apply' };
    let contentHtml = '';
    switch(ce.activeTab) {
        case 'overview': contentHtml = renderCoreOverviewTab(); break;
        case 'inbounds': contentHtml = renderCoreInboundsTab(); break;
        case 'balancers': contentHtml = renderCoreBalancersTab(); break;
        case 'dependencies': contentHtml = renderCoreDepsTab(); break;
        case 'advanced': contentHtml = renderCoreAdvancedTab(); break;
        case 'preview': contentHtml = renderCorePreviewTab(); break;
    }
    return `<div class="full-panel">
        <div class="full-panel-header">
            <h2>${ce.isNew ? 'Create Core' : 'Edit Core: ' + esc(c.name)}</h2>
            <div style="display:flex;gap:8px">
                <button class="btn btn-outline btn-sm" data-action="save-core">Save</button>
                <button class="btn btn-primary btn-sm" data-action="save-apply-core">Save & Apply</button>
                ${!ce.isNew ? '<button class="btn btn-danger btn-sm" data-action="delete-core">Delete</button>' : ''}
                <button class="btn btn-ghost btn-sm" data-action="close-core-editor">${IC.x}</button>
            </div>
        </div>
        <div class="full-panel-body">
            <div class="full-panel-tabs">
                ${tabs.map(t => `<div class="fp-tab${ce.activeTab===t?' active':''}" data-tab="${t}">${tabLabels[t]}${t==='inbounds'?' ('+ce.inbounds.length+')':''}${t==='balancers'?' ('+ce.balancers.length+')':''}${t==='dependencies'?' ('+ce.dependencies.length+')':''}</div>`).join('')}
            </div>
            <div class="full-panel-content">${contentHtml}</div>
        </div>
    </div>`;
}

function renderCoreOverviewTab() {
    const c = S.coreEditor.core;
    const availableNodes = S.nodes || [];
    const nodeOptions = availableNodes.map(n => `<option value="${n.id}" ${c.node_id===n.id?'selected':''}>${esc(n.name)} (${esc(n.address)})</option>`).join('');
    return `<div style="max-width:600px">
        <div class="form-group"><label class="form-label">Name<span class="required">*</span></label><input class="form-input" id="ce-name" value="${esc(c.name)}" maxlength="120"></div>
        <div class="form-group"><label class="form-label">Node<span class="required">*</span></label><select class="form-input" id="ce-node-id"><option value="">Select a node...</option>${nodeOptions}</select><div class="form-hint">One node can only have one enabled core.</div></div>
        <div class="form-group"><label class="form-toggle"><input type="checkbox" id="ce-enabled" ${c.enabled?'checked':''}><span>Enabled</span></label></div>
        ${c.last_applied_at ? `<div class="form-hint mt-12">Last applied: ${fmtTime(c.last_applied_at)}</div>` : ''}
        ${c.last_error ? `<div class="inline-warning mt-12">${IC.alert} <span>${esc(c.last_error)}</span></div>` : ''}
    </div>`;
}

/* ------------------------------------------------------------
   INBOUND TAB
   ------------------------------------------------------------ */
function renderCoreInboundsTab() {
    const ce = S.coreEditor;
    // If editing a specific inbound
    if (S.inboundSubEditor) return renderInboundEditor();
    if (!ce.inbounds.length) return `<div class="empty-state">${IC.cores}<h3>No Inbounds</h3><p>Inbounds define what ports the node listens on and where traffic is forwarded.</p><button class="btn btn-primary" data-action="add-inbound">${IC.plus} Add Inbound</button></div>`;
    let html = `<div style="display:flex;justify-content:flex-end;margin-bottom:12px"><button class="btn btn-primary btn-sm" data-action="add-inbound">${IC.plus} Add Inbound</button></div>`;
    ce.inbounds.forEach((inb, idx) => {
        const listenPreview = inb.port_mode === 'fixed' ? `${esc(inb.bind_ip||'0.0.0.0')}:${portsToStr(inb.fixed_ports)}` : `${esc(inb.bind_ip||'0.0.0.0')}:random × ${inb.random_count}`;
        let advPreview = '';
        if (inb.public_ports_mode === 'use_inbound_ports') advPreview = `advertise: ${esc(inb.public_host || '(node addr)')}:same ports`;
        else if (inb.public_ports_mode === 'fixed') advPreview = `advertise: ${esc(inb.public_host || '(node addr)')}:${portsToStr(inb.public_fixed_ports)}`;
        else advPreview = `advertise: ${esc(inb.public_host || '(node addr)')}:random × ${inb.public_random_count}`;
        const targetPreview = inb.target_type === 'static' ? `→ ${esc(inb.target_host)}:${inb.target_port}` : `→ balancer: ${esc(inb.target_balancer)}`;
        html += `<div class="sub-item">
            <div class="sub-item-header">
                <div class="sub-item-title">${inb.enabled ? '<span class="badge badge-success" style="font-size:0.6rem">ON</span>' : '<span class="badge badge-muted" style="font-size:0.6rem">OFF</span>'}<span class="name">${esc(inb.name)}</span></div>
                <div class="actions-cell">
                    <button class="btn btn-xs btn-ghost" data-action="edit-inbound" data-idx="${idx}">${IC.edit}</button>
                    <button class="btn btn-xs btn-ghost text-error" data-action="delete-inbound" data-idx="${idx}">${IC.trash}</button>
                </div>
            </div>
            <div class="sub-item-body">
                <div class="inbound-preview">
                    <div><span>listen: </span><strong>${listenPreview}</strong></div>
                    <div><span>advertise: </span><strong>${advPreview}</strong></div>
                    <div><span>target: </span><strong>${targetPreview}</strong></div>
                </div>
            </div>
        </div>`;
    });
    return html;
}

function renderInboundEditor() {
    const ie = S.inboundSubEditor;
    const d = ie.data;
    const balancers = S.coreEditor.balancers.filter(b => b.enabled);
    const balOptions = balancers.map(b => `<option value="${esc(b.alias)}" ${d.target_balancer===b.alias?'selected':''}>${esc(b.alias)}</option>`).join('');
    const showFixedPorts = d.port_mode === 'fixed';
    const showRandomCount = d.port_mode === 'random';
    const showPubFixed = d.public_ports_mode === 'fixed';
    const showPubRandom = d.public_ports_mode === 'random';
    const showStaticTarget = d.target_type === 'static';
    const showBalancerTarget = d.target_type === 'balancer';

    return `<div style="max-width:700px">
        <h3 style="font-size:0.95rem;font-weight:700;margin-bottom:16px">${ie.index === -1 ? 'Add Inbound' : 'Edit Inbound'}</h3>
        <div class="form-row">
            <div class="form-group"><label class="form-label">Name<span class="required">*</span></label><input class="form-input" data-ie="name" value="${esc(d.name)}" maxlength="120"></div>
            <div class="form-group"><label class="form-label">Bind IP</label><input class="form-input" data-ie="bind_ip" value="${esc(d.bind_ip)}" maxlength="120" placeholder="0.0.0.0"><div class="form-hint">Local bind address</div></div>
        </div>

        <div style="margin:16px 0 8px;padding:8px 12px;background:var(--accent-soft);border-radius:var(--radius-sm);font-size:0.78rem;font-weight:700;color:var(--accent)">LISTEN PORTS</div>
        <div class="form-row">
            <div class="form-group"><label class="form-label">Port Mode<span class="required">*</span></label><select class="form-input" data-inbound-field="port_mode" data-ie="port_mode"><option value="fixed" ${d.port_mode==='fixed'?'selected':''}>Fixed</option><option value="random" ${d.port_mode==='random'?'selected':''}>Random</option></select></div>
            ${showFixedPorts ? `<div class="form-group" style="grid-column:span 1"><label class="form-label">Fixed Ports<span class="required">*</span></label><input class="form-input" data-ie="fixed_ports" value="${portsToStr(d.fixed_ports)}" placeholder="8080, 8081, 8082"><div class="form-hint">Comma-separated</div></div>` : ''}
            ${showRandomCount ? `<div class="form-group"><label class="form-label">Random Count</label><input type="number" class="form-input" data-ie="random_count" value="${d.random_count}" min="1" max="4096"></div>` : ''}
        </div>

        <div style="margin:20px 0 8px;padding:8px 12px;background:var(--info-soft);border-radius:var(--radius-sm);font-size:0.78rem;font-weight:700;color:var(--info)">PUBLIC ADVERTISED PORTS (for exported routing)</div>
        <div class="form-row">
            <div class="form-group"><label class="form-label">Public Host</label><input class="form-input" data-ie="public_host" value="${esc(d.public_host)}" maxlength="255" placeholder="Leave empty to use node address"><div class="form-hint">Host advertised to other nodes</div></div>
            <div class="form-group"><label class="form-label">Public Ports Mode<span class="required">*</span></label><select class="form-input" data-inbound-field="public_ports_mode" data-ie="public_ports_mode"><option value="use_inbound_ports" ${d.public_ports_mode==='use_inbound_ports'?'selected':''}>Use Inbound Ports</option><option value="random" ${d.public_ports_mode==='random'?'selected':''}>Random</option><option value="fixed" ${d.public_ports_mode==='fixed'?'selected':''}>Fixed</option></select></div>
        </div>
        ${showPubFixed ? `<div class="form-group"><label class="form-label">Public Fixed Ports<span class="required">*</span></label><input class="form-input" data-ie="public_fixed_ports" value="${portsToStr(d.public_fixed_ports)}" placeholder="9080, 9081"><div class="form-hint">Comma-separated</div></div>` : ''}
        ${showPubRandom ? `<div class="form-group" style="max-width:200px"><label class="form-label">Public Random Count</label><input type="number" class="form-input" data-ie="public_random_count" value="${d.public_random_count}" min="1" max="4096"></div>` : ''}

        <div style="margin:20px 0 8px;padding:8px 12px;background:var(--warning-soft);border-radius:var(--radius-sm);font-size:0.78rem;font-weight:700;color:var(--warning)">TARGET</div>
        <div class="form-group"><label class="form-label">Target Type<span class="required">*</span></label><select class="form-input" data-inbound-field="target_type" data-ie="target_type"><option value="static" ${d.target_type==='static'?'selected':''}>Static</option><option value="balancer" ${d.target_type==='balancer'?'selected':''}>Balancer</option></select></div>
        ${showStaticTarget ? `<div class="form-row">
            <div class="form-group"><label class="form-label">Target Host<span class="required">*</span></label><input class="form-input" data-ie="target_host" value="${esc(d.target_host)}" maxlength="255"></div>
            <div class="form-group"><label class="form-label">Target Port<span class="required">*</span></label><input type="number" class="form-input" data-ie="target_port" value="${d.target_port}" min="1" max="65535"></div>
        </div>` : ''}
        ${showBalancerTarget ? `<div class="form-group"><label class="form-label">Target Balancer<span class="required">*</span></label><select class="form-input" data-ie="target_balancer"><option value="">Select balancer...</option>${balOptions}</select>${!balancers.length ? '<div class="form-hint text-warning">No enabled balancers. Create one in the Balancers tab first.</div>' : ''}</div>` : ''}

        <div class="form-group mt-16"><label class="form-toggle"><input type="checkbox" data-ie-enabled="enabled" ${d.enabled?'checked':''}><span>Enabled</span></label></div>
        <div class="form-group"><label class="form-label">Notes</label><textarea class="form-input" data-ie="notes" maxlength="500" rows="2">${esc(d.notes)}</textarea></div>

        <div style="display:flex;gap:8px;margin-top:20px">
            <button class="btn btn-primary" data-action="save-inbound">${ie.index === -1 ? 'Add Inbound' : 'Update Inbound'}</button>
            <button class="btn btn-outline" data-action="cancel-inbound">Cancel</button>
        </div>
    </div>`;
}

function saveInbound() {
    const ie = S.inboundSubEditor;
    const d = ie.data;
    // Read values from DOM
    document.querySelectorAll('[data-ie]').forEach(el => {
        const key = el.dataset.ie;
        if (el.type === 'checkbox') return;
        if (key === 'fixed_ports' || key === 'public_fixed_ports') {
            d[key] = parsePorts(el.value);
        } else if (key === 'random_count' || key === 'public_random_count' || key === 'target_port') {
            d[key] = parseInt(el.value) || 0;
        } else {
            d[key] = el.value;
        }
    });
    document.querySelectorAll('[data-ie-enabled]').forEach(el => { d[el.dataset.ieEnabled] = el.checked; });

    // Validate
    if (!d.name || d.name.trim().length < 1) { toast('Inbound name is required','error'); return; }
    if (d.port_mode === 'fixed' && d.fixed_ports.length === 0) { toast('Fixed ports list cannot be empty','error'); return; }
    if (d.public_ports_mode === 'fixed' && d.public_fixed_ports.length === 0) { toast('Public fixed ports list cannot be empty','error'); return; }
    if (d.target_type === 'static' && (!d.target_host || d.target_port < 1 || d.target_port > 65535)) { toast('Static target host and port are required','error'); return; }
    if (d.target_type === 'balancer' && !d.target_balancer) { toast('Select a target balancer','error'); return; }

    if (ie.index === -1) S.coreEditor.inbounds.push(d);
    else S.coreEditor.inbounds[ie.index] = d;
    S.inboundSubEditor = null;
    renderOverlay();
    toast('Inbound saved','success');
}

/* ------------------------------------------------------------
   BALANCER TAB
   ------------------------------------------------------------ */
function renderCoreBalancersTab() {
    const ce = S.coreEditor;
    // If editing endpoint
    if (S.balancerSubEditor && S.balancerSubEditor.epIdx >= 0) return renderEndpointEditor();
    // If editing balancer header
    if (S.balancerSubEditor && S.balancerSubEditor.epIdx === -1) return renderBalancerHeaderEditor();

    if (!ce.balancers.length) return `<div class="empty-state">${IC.cores}<h3>No Balancers</h3><p>Balancers distribute traffic across multiple endpoints with various strategies.</p><button class="btn btn-primary" data-action="add-balancer">${IC.plus} Add Balancer</button></div>`;
    let html = `<div style="display:flex;justify-content:flex-end;margin-bottom:12px"><button class="btn btn-primary btn-sm" data-action="add-balancer">${IC.plus} Add Balancer</button></div>`;
    ce.balancers.forEach((bal, bi) => {
        const enabledEps = bal.endpoints.filter(e => e.enabled).length;
        html += `<div class="sub-item">
            <div class="sub-item-header">
                <div class="sub-item-title">${bal.enabled ? '<span class="badge badge-success" style="font-size:0.6rem">ON</span>' : '<span class="badge badge-muted" style="font-size:0.6rem">OFF</span>'}<span class="name">${esc(bal.alias)}</span><span class="badge badge-info" style="font-size:0.6rem">${esc(bal.strategy)}</span><span class="text-muted text-xs">${enabledEps}/${bal.endpoints.length} eps</span></div>
                <div class="actions-cell">
                    <button class="btn btn-xs btn-ghost" data-action="edit-balancer" data-idx="${bi}">${IC.edit}</button>
                    <button class="btn btn-xs btn-ghost text-error" data-action="delete-balancer" data-idx="${bi}">${IC.trash}</button>
                </div>
            </div>
            <div class="sub-item-body">
                ${!bal.endpoints.length ? '<div class="text-muted text-sm" style="padding:4px 0">No endpoints</div>' : ''}
                ${bal.endpoints.map((ep, ei) => {
                    let epDesc = '';
                    if (ep.type === 'static') epDesc = `static: ${esc(ep.host)}:${ep.port}`;
                    else {
                        const dep = ce.dependencies.find(d => d.id === ep.dependency_id);
                        const depNode = dep ? getNodeById(dep.ref_id) : null;
                        epDesc = `node_inbound: ${dep ? esc(dep.name) : '?'} → ${esc(ep.inbound_name || '?')}`;
                    }
                    return `<div style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;font-size:0.8rem;border-bottom:1px solid var(--border-subtle)">
                        <div style="display:flex;align-items:center;gap:6px">
                            ${ep.enabled ? '<span class="badge badge-success" style="font-size:0.55rem">ON</span>' : '<span class="badge badge-muted" style="font-size:0.55rem">OFF</span>'}
                            <span class="mono text-xs">${epDesc}</span>
                            <span class="text-muted text-xs">w:${ep.weight}</span>
                        </div>
                        <div class="actions-cell">
                            <button class="btn btn-xs btn-ghost" data-action="edit-endpoint" data-balidx="${bi}" data-epidx="${ei}">${IC.edit}</button>
                            <button class="btn btn-xs btn-ghost text-error" data-action="delete-endpoint" data-balidx="${bi}" data-epidx="${ei}">${IC.trash}</button>
                        </div>
                    </div>`;
                }).join('')}
                <div style="margin-top:8px"><button class="btn btn-xs btn-outline" data-action="add-endpoint" data-balidx="${bi}">${IC.plus} Add Endpoint</button></div>
            </div>
        </div>`;
    });
    return html;
}

function renderBalancerHeaderEditor() {
    const bi = S.balancerSubEditor.balIdx;
    const bal = S.coreEditor.balancers[bi];
    if (!bal) return '<div class="inline-warning">Balancer not found</div>';
    return `<div style="max-width:500px">
        <h3 style="font-size:0.95rem;font-weight:700;margin-bottom:16px">Edit Balancer: ${esc(bal.alias)}</h3>
        <div class="form-group"><label class="form-label">Alias<span class="required">*</span></label><input class="form-input" data-bal="alias" value="${esc(bal.alias)}" maxlength="120"></div>
        <div class="form-group"><label class="form-label">Strategy<span class="required">*</span></label><select class="form-input" data-bal="strategy">
            ${['round_robin','random','failover','least_connections'].map(s => `<option value="${s}" ${bal.strategy===s?'selected':''}>${s.replace('_',' ')}</option>`).join('')}
        </select></div>
        <div class="form-group"><label class="form-toggle"><input type="checkbox" data-bal-enabled="enabled" ${bal.enabled?'checked':''}><span>Enabled</span></label></div>
        <div class="form-group"><label class="form-label">Notes</label><textarea class="form-input" data-bal="notes" maxlength="500" rows="2">${esc(bal.notes)}</textarea></div>
        <div style="display:flex;gap:8px;margin-top:20px">
            <button class="btn btn-primary" data-action="save-balancer">Update Balancer</button>
            <button class="btn btn-outline" data-action="cancel-balancer">Cancel</button>
        </div>
    </div>`;
}

function saveBalancer() {
    const bi = S.balancerSubEditor.balIdx;
    const bal = S.coreEditor.balancers[bi];
    document.querySelectorAll('[data-bal]').forEach(el => { bal[el.dataset.bal] = el.value; });
    document.querySelectorAll('[data-bal-enabled]').forEach(el => { bal[el.dataset.balEnabled] = el.checked; });
    if (!bal.alias || bal.alias.trim().length < 1) { toast('Balancer alias is required','error'); return; }
    S.balancerSubEditor = null;
    renderOverlay();
    toast('Balancer updated','success');
}

/* ------------------------------------------------------------
   ENDPOINT EDITOR
   ------------------------------------------------------------ */
function renderEndpointEditor() {
    const { balIdx, epIdx } = S.balancerSubEditor;
    const ep = S.coreEditor.balancers[balIdx]?.endpoints[epIdx];
    if (!ep) return '<div class="inline-warning">Endpoint not found</div>';
    const ce = S.coreEditor;
    const isStatic = ep.type === 'static';
    const depOptions = ce.dependencies.map(d => {
        const n = getNodeById(d.ref_id);
        return `<option value="${d.id}" ${ep.dependency_id===d.id?'selected':''}>${esc(d.name)} → ${n ? esc(n.name) : 'Unknown Node'}</option>`;
    }).join('');
    const selectedDep = ce.dependencies.find(d => d.id === ep.dependency_id);
    const depNodeId = selectedDep ? selectedDep.ref_id : '';
    const catalogInbounds = depNodeId ? getCatalogForNode(depNodeId) : [];
    // Group by core
    let inboundOptions = '';
    if (catalogInbounds.length) {
        const byCore = {};
        catalogInbounds.forEach(ci => { const k = ci.core_id || '_unknown'; if (!byCore[k]) byCore[k] = []; byCore[k].push(ci); });
        Object.entries(byCore).forEach(([coreId, inbs]) => {
            const coreObj = inbs[0]?.core_name || coreId;
            inboundOptions += `<optgroup label="${esc(coreObj)}">`;
            inbs.forEach(ci => { inboundOptions += `<option value="${esc(ci.name)}" ${ep.inbound_name===ci.name && ep.core_id===coreId?'selected':''}>${esc(ci.name)} ${ci.public_ports_mode==='fixed' ? portsToStr(ci.public_fixed_ports||ci.fixed_ports||[]) : ci.port_mode==='random' ? 'random×'+ci.random_count : ''}</option>`; });
            inboundOptions += '</optgroup>';
        });
    }

    if (!isStatic && !ce.dependencies.length) {
        return `<div style="max-width:500px">
            <h3 style="font-size:0.95rem;font-weight:700;margin-bottom:16px">Edit Endpoint</h3>
            <div class="inline-info">${IC.eye} <span>Add a node dependency in the Dependencies tab before using Node Inbound endpoints.</span></div>
            <div style="display:flex;gap:8px;margin-top:16px">
                <button class="btn btn-outline" data-action="cancel-endpoint">Cancel</button>
            </div>
        </div>`;
    }

    return `<div style="max-width:600px">
        <h3 style="font-size:0.95rem;font-weight:700;margin-bottom:16px">${epIdx === -1 ? 'Add' : 'Edit'} Endpoint</h3>
        <div class="form-group"><label class="form-label">Type<span class="required">*</span></label><select class="form-input" data-ep-field="type"><option value="static" ${isStatic?'selected':''}>Static</option><option value="node_inbound" ${!isStatic?'selected':''}>Node Inbound</option></select></div>
        ${isStatic ? `<div class="form-row">
            <div class="form-group"><label class="form-label">Host<span class="required">*</span></label><input class="form-input" data-ep="host" value="${esc(ep.host)}" maxlength="255"></div>
            <div class="form-group"><label class="form-label">Port<span class="required">*</span></label><input type="number" class="form-input" data-ep="port" value="${ep.port}" min="1" max="65535"></div>
        </div>` : `
        <div class="form-group"><label class="form-label">Dependency<span class="required">*</span></label><select class="form-input" data-ep-dep="dependency_id"><option value="">Select dependency...</option>${depOptions}</select><div class="form-hint">Select from dependencies defined in the Dependencies tab</div></div>
        ${depNodeId ? `<div class="form-group"><label class="form-label">Core / Inbound<span class="required">*</span></label><select class="form-input" data-ep-inbound="inbound_name"><option value="">Select inbound...</option>${inboundOptions}</select></div>` : '<div class="form-hint">Select a dependency to see available inbounds</div>'}
        `}
        <div class="form-row">
            <div class="form-group"><label class="form-label">Weight</label><input type="number" class="form-input" data-ep="weight" value="${ep.weight}" min="0" step="0.1"></div>
            <div class="form-group"><label class="form-toggle" style="margin-top:22px"><input type="checkbox" data-ep-enabled="enabled" ${ep.enabled?'checked':''}><span>Enabled</span></label></div>
        </div>
        <div class="form-group"><label class="form-label">Notes</label><textarea class="form-input" data-ep="notes" maxlength="500" rows="2">${esc(ep.notes)}</textarea></div>
        <div style="display:flex;gap:8px;margin-top:20px">
            <button class="btn btn-primary" data-action="save-endpoint">Save Endpoint</button>
            <button class="btn btn-outline" data-action="cancel-endpoint">Cancel</button>
        </div>
    </div>`;
}

function saveEndpoint() {
    const { balIdx, epIdx } = S.balancerSubEditor;
    const ep = S.coreEditor.balancers[balIdx].endpoints[epIdx];
    document.querySelectorAll('[data-ep]').forEach(el => {
        const k = el.dataset.ep;
        if (k === 'port' || k === 'weight') ep[k] = parseFloat(el.value) || 0;
        else ep[k] = el.value;
    });
    document.querySelectorAll('[data-ep-enabled]').forEach(el => { ep[el.dataset.epEnabled] = el.checked; });
    document.querySelectorAll('[data-ep-dep]').forEach(el => {
        ep.dependency_id = el.value;
        if (el.value) {
            const dep = S.coreEditor.dependencies.find(d => d.id === el.value);
            ep.node_id = dep ? dep.ref_id : '';
        } else {
            ep.node_id = '';
        }
    });
    document.querySelectorAll('[data-ep-inbound]').forEach(el => {
        ep.inbound_name = el.value;
        // Try to find core_id from catalog
        if (el.value && ep.node_id) {
            const catalog = getCatalogForNode(ep.node_id);
            const found = catalog.find(ci => ci.name === el.value);
            ep.core_id = found?.core_id || '';
        }
    });

    // Validate
    if (ep.type === 'static') {
        if (!ep.host) { toast('Host is required for static endpoint','error'); return; }
        if (ep.port < 1 || ep.port > 65535) { toast('Port must be 1-65535','error'); return; }
        ep.dependency_id = ''; ep.node_id = ''; ep.core_id = ''; ep.inbound_name = '';
    } else {
        if (!ep.dependency_id) { toast('Select a dependency','error'); return; }
        if (!ep.inbound_name) { toast('Select an inbound','error'); return; }
        ep.host = ''; ep.port = 80;
    }

    S.balancerSubEditor = { balIdx, epIdx: -1 };
    renderOverlay();
    toast('Endpoint saved','success');
}

/* ------------------------------------------------------------
   DEPENDENCY TAB
   ------------------------------------------------------------ */
function renderCoreDepsTab() {
    const ce = S.coreEditor;
    const currentNodeId = ce.core.node_id;
    const availableNodes = S.nodes.filter(n => n.id !== currentNodeId);

    // If editing a dependency
    if (S.depSubEditor && S.depSubEditor.data === null) {
        const idx = S.depSubEditor.index;
        const dep = idx >= 0 ? ce.dependencies[idx] : null;
        if (!dep && idx >= 0) { S.depSubEditor = null; return renderCoreDepsTab(); }
        const d = dep || defaultDependency(ce.dependencies.length);
        const nodeOpts = availableNodes.map(n => `<option value="${n.id}" ${d.ref_id===n.id?'selected':''}>${esc(n.name)} (${esc(n.address)})</option>`).join('');
        return `<div style="max-width:600px">
            <h3 style="font-size:0.95rem;font-weight:700;margin-bottom:16px">${idx === -1 ? 'Add' : 'Edit'} Dependency</h3>
            <div class="form-group"><label class="form-label">Name</label><input class="form-input" data-dep="name" value="${esc(d.name)}" maxlength="120" placeholder="dep 1"><div class="form-hint">A label for this dependency instance</div></div>
            <div class="form-group"><label class="form-label">Remote Node<span class="required">*</span></label><select class="form-input" data-dep-field="ref_id" data-dep="ref_id"><option value="">Select node...</option>${nodeOpts}</select><div class="form-hint">The node this core depends on. Same node can be added multiple times with different host overrides.</div></div>
            <div class="form-group"><label class="form-label">Host Override</label><input class="form-input" data-dep="host" value="${esc(d.host)}" maxlength="255" placeholder="Leave empty to use advertised host"><div class="form-hint">Override the host used to reach this dependency</div></div>
            <div class="form-row">
                <div class="form-group"><label class="form-label">Sync Interval (s)</label><input type="number" class="form-input" data-dep="sync_interval" value="${d.sync_interval}" min="1" max="86400"><div class="form-hint">How often to sync runtime from this dependency</div></div>
                <div class="form-group"><label class="form-toggle" style="margin-top:22px"><input type="checkbox" data-dep-req="required" ${d.required?'checked':''}><span>Required</span></label></div>
            </div>
            <div class="form-group"><label class="form-label">Notes</label><textarea class="form-input" data-dep="notes" maxlength="500" rows="2">${esc(d.notes)}</textarea></div>
            <div style="display:flex;gap:8px;margin-top:20px">
                <button class="btn btn-primary" data-action="save-dep">${idx === -1 ? 'Add Dependency' : 'Update Dependency'}</button>
                <button class="btn btn-outline" data-action="cancel-dep">Cancel</button>
            </div>
        </div>`;
    }

    if (!ce.dependencies.length) return `<div class="empty-state">${IC.cores}<h3>No Dependencies</h3><p>Dependencies define which remote nodes this core relies on. They are needed for Node Inbound balancer endpoints.</p><button class="btn btn-primary" data-action="add-dep">${IC.plus} Add Dependency</button></div>`;
    let html = `<div style="display:flex;justify-content:flex-end;margin-bottom:12px"><button class="btn btn-primary btn-sm" data-action="add-dep">${IC.plus} Add Dependency</button></div>`;
    ce.dependencies.forEach((dep, idx) => {
        const remoteNode = getNodeById(dep.ref_id);
        html += `<div class="sub-item">
            <div class="sub-item-header">
                <div class="sub-item-title">${dep.required ? '<span class="badge badge-warning" style="font-size:0.55rem">REQ</span>' : '<span class="badge badge-muted" style="font-size:0.55rem">OPT</span>'}<span class="name">${esc(dep.name)}</span><span class="text-muted text-xs">→ ${remoteNode ? esc(remoteNode.name) : '<span class="text-error">Missing</span>'}</span></div>
                <div class="actions-cell">
                    <button class="btn btn-xs btn-ghost" data-action="edit-dep" data-idx="${idx}">${IC.edit}</button>
                    <button class="btn btn-xs btn-ghost text-error" data-action="delete-dep" data-idx="${idx}">${IC.trash}</button>
                </div>
            </div>
            <div class="sub-item-body">
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;font-size:0.8rem">
                    <div><span class="text-muted">Host Override:</span> ${dep.host ? esc(dep.host) : '<span class="text-muted">(default)</span>'}</div>
                    <div><span class="text-muted">Sync Interval:</span> ${dep.sync_interval}s</div>
                </div>
            </div>
        </div>`;
    });
    return html;
}

function saveDependency() {
    const idx = S.depSubEditor.index;
    let d;
    if (idx === -1) {
        d = defaultDependency(S.coreEditor.dependencies.length);
        S.coreEditor.dependencies.push(d);
    } else {
        d = S.coreEditor.dependencies[idx];
    }
    document.querySelectorAll('[data-dep]').forEach(el => {
        const k = el.dataset.dep;
        if (k === 'sync_interval') d[k] = parseInt(el.value) || 5;
        else d[k] = el.value;
    });
    document.querySelectorAll('[data-dep-req]').forEach(el => { d.required = el.checked; });
    if (!d.ref_id) { toast('Select a remote node','error'); return; }
    if (d.ref_id === S.coreEditor.core.node_id) { toast('Cannot depend on the same node','error'); return; }
    S.depSubEditor = null;
    renderOverlay();
    toast('Dependency saved','success');
}

/* ------------------------------------------------------------
   ADVANCED JSON TAB
   ------------------------------------------------------------ */
function renderCoreAdvancedTab() {
    const adv = S.coreEditor.advanced;
    return `<div style="max-width:800px">
        <div class="form-group"><label class="form-toggle"><input type="checkbox" id="adv-enabled" ${adv.enabled?'checked':''}><span>Enable Advanced JSON Configuration</span></label><div class="form-hint">When enabled, this JSON will be merged into the core config sent to the node.</div></div>
        <div class="form-group"><label class="form-label">JSON Configuration${adv.enabled?'<span class="required">*</span>':''}</label>
            <textarea class="form-input" id="adv-json" style="font-family:var(--font-mono);font-size:0.8rem;min-height:300px;line-height:1.6" ${!adv.enabled?'disabled':''}>${esc(adv.json_config)}</textarea>
            <div class="form-hint">Max 200,000 characters</div>
        </div>
        <div style="display:flex;gap:8px">
            <button class="btn btn-outline" data-action="validate-json-local">Validate Locally</button>
            <button class="btn btn-outline" data-action="validate-json-backend">Validate on Server</button>
        </div>
        <div id="adv-validation-result" style="margin-top:12px"></div>
    </div>`;
}

function validateJsonLocal() {
    const json = document.getElementById('adv-json').value;
    const resultEl = document.getElementById('adv-validation-result');
    if (!json.trim()) { resultEl.innerHTML = '<div class="inline-warning">JSON is empty</div>'; return; }
    try {
        const parsed = JSON.parse(json);
        resultEl.innerHTML = `<div class="inline-info" style="margin-top:12px">${IC.check} <span>Valid JSON — ${Object.keys(parsed).length} top-level keys</span></div>`;
    } catch(e) {
        resultEl.innerHTML = `<div class="inline-warning" style="margin-top:12px">${IC.alert} <span>Invalid JSON: ${esc(e.message)}</span></div>`;
    }
}

async function validateJsonBackend() {
    const json = document.getElementById('adv-json').value;
    const resultEl = document.getElementById('adv-validation-result');
    if (!json.trim()) { resultEl.innerHTML = '<div class="inline-warning">JSON is empty</div>'; return; }
    try {
        JSON.parse(json); // local check first
    } catch(e) {
        resultEl.innerHTML = `<div class="inline-warning" style="margin-top:12px">${IC.alert} <span>Fix local JSON errors first: ${esc(e.message)}</span></div>`;
        return;
    }
    try {
        await API.cores.validateAdv({ json_config: json });
        resultEl.innerHTML = `<div class="inline-info" style="margin-top:12px">${IC.check} <span>Server validation passed</span></div>`;
    } catch(e) {
        resultEl.innerHTML = `<div class="inline-warning" style="margin-top:12px">${IC.alert} <span>${esc(e.detail || 'Validation failed')}</span></div>`;
    }
}

/* ------------------------------------------------------------
   PREVIEW / APPLY TAB
   ------------------------------------------------------------ */
function renderCorePreviewTab() {
    const ce = S.coreEditor;
    let html = `<div style="max-width:800px">
        <p class="text-secondary text-sm mb-16">Preview the full configuration that will be sent to the node, or apply it directly.</p>
        <div style="display:flex;gap:8px;margin-bottom:16px">
            <button class="btn btn-outline" data-action="preview-core">${IC.eye} Preview Config</button>
            ${!ce.isNew ? `<button class="btn btn-warning" data-action="apply-core-now">${IC.upload} Apply to Node</button>` : '<div class="text-muted text-sm">Save the core first before applying.</div>'}
        </div>
        <div id="core-preview-result"></div>
    </div>`;
    return html;
}

async function previewCore() {
    const resultEl = document.getElementById('core-preview-result');
    if (!resultEl) return;
    resultEl.innerHTML = '<div class="spinner" style="margin:20px 0"></div>';
    // We need to save first to get a preview, or build the payload
    const payload = buildCorePayload();
    if (!payload) return;
    if (S.coreEditor.isNew) {
        // For new cores, just show the payload we'd send
        resultEl.innerHTML = `<div class="code-block-header"><span>Payload Preview (new core — save first for server-side preview)</span><button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.code-block-header').nextElementSibling.textContent).then(()=>toast('Copied','success'))">${IC.copy} Copy</button></div><pre class="code-block">${esc(JSON.stringify(payload, null, 2))}</pre>`;
        return;
    }
    try {
        const data = await API.cores.preview(S.coreEditor.core.id);
        const json = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
        resultEl.innerHTML = `<div class="code-block-header"><span>Config Preview</span><button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.code-block-header').nextElementSibling.textContent).then(()=>toast('Copied','success'))">${IC.copy} Copy</button></div><pre class="code-block">${esc(json)}</pre>`;
    } catch(e) {
        resultEl.innerHTML = `<div class="inline-warning">${IC.alert} <span>${esc(e.detail || 'Preview failed. Save the core first.')}</span></div>`;
    }
}

async function applyCoreNow() {
    if (S.coreEditor.isNew) { toast('Save the core first','warning'); return; }
    showConfirm({ title:'Apply Core Config', text:'Push the current core configuration to the node. This will update the running config.', icon:'warning', confirmText:'Apply', onConfirm: async () => {
        try {
            await API.cores.apply(S.coreEditor.core.id);
            toast('Core config applied','success');
            await loadDashboardData();
        } catch(e) { toast(e.detail || 'Apply failed','error'); }
    }});
}

function buildCorePayload() {
    const c = S.coreEditor.core;
    const name = document.getElementById('ce-name')?.value.trim() || c.name;
    const node_id = document.getElementById('ce-node-id')?.value || c.node_id;
    const enabled = document.getElementById('ce-enabled')?.checked ?? c.enabled;
    const advEnabled = document.getElementById('adv-enabled')?.checked ?? S.coreEditor.advanced.enabled;
    const advJson = document.getElementById('adv-json')?.value ?? S.coreEditor.advanced.json_config;
    if (!name) { toast('Core name is required','error'); return null; }
    if (!node_id) { toast('Select a node','error'); return null; }
    return {
        name,
        node_id,
        enabled,
        inbounds: S.coreEditor.inbounds,
        balancers: S.coreEditor.balancers,
        dependencies: S.coreEditor.dependencies,
        advanced: { enabled: advEnabled, json_config: advJson },
    };
}

async function saveCore(applyAfter) {
    const payload = buildCorePayload();
    if (!payload) return;
    try {
        if (S.coreEditor.isNew) {
            const created = await API.cores.create(payload);
            toast('Core created','success');
            if (applyAfter && created?.id) {
                try { await API.cores.apply(created.id); toast('Core applied','success'); } catch(e) { toast(e.detail||'Created but apply failed','warning'); }
            }
        } else {
            await API.cores.update(S.coreEditor.core.id, payload);
            toast('Core saved','success');
            if (applyAfter) {
                try { await API.cores.apply(S.coreEditor.core.id); toast('Core applied','success'); } catch(e) { toast(e.detail||'Saved but apply failed','warning'); }
            }
        }
        S.coreEditor.open = false;
        await loadDashboardData();
        renderOverlay();
        renderPageContent();
    } catch(e) { toast(e.detail || 'Save failed','error'); }
}

function deleteCore() {
    if (S.coreEditor.isNew) { S.coreEditor.open = false; renderOverlay(); return; }
    const c = S.coreEditor.core;
    showConfirm({ title:'Delete Core', text:`Permanently delete "${c.name}" and all its inbounds, balancers, and dependencies?`, confirmText:'Delete', onConfirm: async () => {
        try { await API.cores.delete(c.id); toast('Core deleted','success'); S.coreEditor.open = false; await loadDashboardData(); renderOverlay(); renderPageContent(); } catch(e) { toast(e.detail||'Delete failed','error'); }
    }});
}

/* ------------------------------------------------------------
   LOGS PAGE
   ------------------------------------------------------------ */
function renderLogs() {
    const f = S.logsFilter;
    const sourceOptions = S.logsSources.map(s => `<option value="${esc(s)}" ${f.source===s?'selected':''}>${esc(s)}</option>`).join('');
    const levelOptions = ['all','debug','info','warning','error'].map(l => `<option value="${l}" ${f.level===l?'selected':''}>${l}</option>`).join('');
    const entries = S.logsEntries || [];
    const lines = Array.isArray(entries) ? entries : (entries.logs || entries.entries || []);
    return `<div class="card mb-16">
        <div class="card-body compact">
            <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center">
                <div class="form-group" style="margin:0;min-width:140px"><select class="form-input" id="log-source" style="padding:6px 10px;font-size:0.8rem"><option value="panel">panel</option>${sourceOptions}</select></div>
                <div class="form-group" style="margin:0;min-width:100px"><select class="form-input" id="log-level" style="padding:6px 10px;font-size:0.8rem">${levelOptions}</select></div>
                <div class="form-group" style="margin:0;min-width:80px"><input type="number" class="form-input" id="log-limit" value="${f.limit}" min="1" max="5000" style="padding:6px 10px;font-size:0.8rem"></div>
                <div class="form-group" style="margin:0;flex:1;min-width:200px"><input class="form-input" id="log-q" value="${esc(f.q)}" placeholder="Search..." style="padding:6px 10px;font-size:0.8rem"></div>
                <button class="btn btn-primary btn-sm" id="log-search-btn">${IC.search} Search</button>
                <button class="btn btn-outline btn-sm" id="log-refresh-btn">${IC.refresh}</button>
            </div>
        </div>
    </div>
    <div class="card">
        <div class="card-header">
            <h3>Log Output</h3>
            <div style="display:flex;gap:8px;align-items:center">
                <span class="text-muted text-xs">${lines.length} lines</span>
                <button class="btn btn-xs btn-ghost" id="log-copy-btn">${IC.copy} Copy</button>
            </div>
        </div>
        <div style="max-height:calc(100vh - 280px);overflow-y:auto" id="log-lines">
            ${lines.length ? lines.map(l => {
                const lvl = (l.level || 'info').toLowerCase();
                return `<div class="log-line level-${lvl}"><span class="log-ts">${esc(l.timestamp || l.ts || '')}</span><span class="log-level ${lvl}">${esc(l.level || 'info')}</span><span class="log-msg">${esc(l.message || l.msg || JSON.stringify(l))}</span></div>`;
            }).join('') : '<div class="empty-state"><p>No log entries. Adjust filters and search.</p></div>'}
        </div>
    </div>`;
}
function bindLogsEvents() {
    const doSearch = () => {
        S.logsFilter.source = document.getElementById('log-source').value;
        S.logsFilter.level = document.getElementById('log-level').value;
        S.logsFilter.limit = parseInt(document.getElementById('log-limit').value) || 300;
        S.logsFilter.q = document.getElementById('log-q').value.trim();
        loadLogs().then(() => renderPageContent());
    };
    document.getElementById('log-search-btn')?.addEventListener('click', doSearch);
    document.getElementById('log-refresh-btn')?.addEventListener('click', doSearch);
    document.getElementById('log-q')?.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });
    document.getElementById('log-copy-btn')?.addEventListener('click', () => {
        const lines = document.getElementById('log-lines');
        if (lines) navigator.clipboard.writeText(lines.textContent).then(() => toast('Logs copied','success')).catch(() => toast('Copy failed','error'));
    });
}

/* ------------------------------------------------------------
   DIAGNOSTICS PAGE
   ------------------------------------------------------------ */
function renderDiagnostics() {
    const integ = S.integrity;
    let integHtml = '';
    if (integ && integ.issues && integ.issues.length) {
        integHtml = `<div class="card mb-16">
            <div class="card-header"><h3>Integrity Issues</h3><button class="btn btn-danger btn-sm" id="repair-btn">${IC.wrench} Repair Data</button></div>
            <div class="card-body compact">
                ${integ.issues.map(i => `<div class="integrity-item issue"><span class="ii-icon text-error">${IC.alert}</span><span>${esc(typeof i === 'string' ? i : i.message || i.description || JSON.stringify(i))}</span></div>`).join('')}
            </div>
        </div>`;
    } else if (integ) {
        integHtml = `<div class="card mb-16"><div class="card-body compact"><div class="integrity-item ok"><span class="ii-icon text-accent">${IC.check}</span><span>No integrity issues detected.</span></div></div></div>`;
    } else {
        integHtml = `<div class="card mb-16"><div class="card-body compact"><span class="text-muted text-sm">Integrity check not yet run.</span></div></div>`;
    }

    // Runtime health summary
    const nodes = S.nodes || [];
    const rc = S.runtimeCache || {};
    let rtHtml = '<div class="card mb-16"><div class="card-header"><h3>Runtime Health Summary</h3></div><div class="card-body compact">';
    if (!nodes.length) {
        rtHtml += '<div class="text-muted text-sm">No nodes to check.</div>';
    } else {
        nodes.forEach(n => {
            const rt = rc[n.id];
            const ok = rt?.runtime_ok;
            rtHtml += `<div style="display:flex;align-items:center;gap:10px;padding:6px 0;font-size:0.82rem;border-bottom:1px solid var(--border-subtle)">
                ${ok ? '<span class="badge badge-success"><span class="badge-dot pulse"></span>OK</span>' : '<span class="badge badge-error">Issue</span>'}
                <strong>${esc(n.name)}</strong>
                <span class="text-muted">${esc(n.address)}</span>
                ${rt?.reachable !== undefined ? `<span class="text-xs">reachable:${rt.reachable?'✓':'✗'}</span>` : ''}
                ${rt?.auth_ok !== undefined ? `<span class="text-xs">auth:${rt.auth_ok?'✓':'✗'}</span>` : ''}
                ${rt?.last_error ? `<span class="text-error text-xs">${esc(rt.last_error.slice(0,80))}</span>` : ''}
            </div>`;
        });
    }
    rtHtml += '</div></div>';

    return `<div style="display:flex;justify-content:flex-end;gap:8px;margin-bottom:14px">
        <button class="btn btn-outline" id="check-integrity-btn">${IC.eye} Check Integrity</button>
        <button class="btn btn-outline" id="sync-all-btn">${IC.sync} Sync All Runtime</button>
    </div>
    ${integHtml}
    ${rtHtml}`;
}
function bindDiagnosticsEvents() {
    document.getElementById('check-integrity-btn')?.addEventListener('click', async () => {
        await loadIntegrity();
        renderPageContent();
    });
    document.getElementById('repair-btn')?.addEventListener('click', () => {
        showConfirm({ title:'Repair Data', text:'This will attempt to fix data integrity issues. The operation may modify stored configurations.', icon:'warning', confirmText:'Repair', onConfirm: async () => {
            try { await API.panel.repair(); toast('Repair completed','success'); await loadIntegrity(); await loadDashboardData(); renderPageContent(); } catch(e) { toast(e.detail||'Repair failed','error'); }
        }});
    });
    document.getElementById('sync-all-btn')?.addEventListener('click', async () => {
        try { await API.nodes.syncAll(); toast('All runtimes synced','success'); await loadDashboardData(); renderPageContent(); } catch(e) { toast(e.detail||'Sync failed','error'); }
    });
}

/* ------------------------------------------------------------
   INITIALIZATION
   ------------------------------------------------------------ */
async function init() {
    try {
        S.user = await API.auth.me();
    } catch(e) {
        S.user = null;
    }
    renderApp();
    if (S.user) {
        await loadDashboardData();
        await loadLogsSources();
        renderPageContent();
    }
}

// Boot
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

})();
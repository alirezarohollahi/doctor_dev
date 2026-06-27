const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = {
  user: null,
  nodes: [],
  cores: [],
  inboundCatalog: [],
  page: 'dashboard',
  editingNode: null,
  editingCore: null,
  editorDraft: null,
  lastFormCheck: null,
  currentCoreTab: 'inbounds',
};

const loginView = $('#loginView');
const appView = $('#appView');
const loginForm = $('#loginForm');
const loginMessage = $('#loginMessage');
const submitButton = $('#submitButton');
const adminName = $('#adminName');
const logoutButton = $('#logoutButton');
const togglePassword = $('#togglePassword');
const passwordInput = $('#password');
const pageTitle = $('#pageTitle');
const nodeModal = $('#nodeModal');
const nodeForm = $('#nodeForm');
const nodeMessage = $('#nodeMessage');
const coreCreateModal = $('#coreCreateModal');
const coreCreateForm = $('#coreCreateForm');
const coreCreateMessage = $('#coreCreateMessage');
const coreEditorMessage = $('#coreEditorMessage');

function setMessage(element, text, type = '') { if (!element) return; element.textContent = text || ''; element.className = `message ${type}`.trim(); }
async function api(path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || 'Request failed.');
  return data;
}
function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char])); }
function nodeById(id) { return state.nodes.find(n => n.id === id) || null; }
function coreById(id) { return state.cores.find(c => c.id === id) || null; }
function nodeName(id) { return (nodeById(id) || {}).name || 'Unknown node'; }
function deepCopy(value) { return JSON.parse(JSON.stringify(value || {})); }
function cleanId(value) { return String(value || '').replace(/[^a-zA-Z0-9_-]/g, '_'); }

function showApp(username) { state.user = username || 'admin'; adminName.textContent = state.user; loginView.classList.add('hidden'); appView.classList.remove('hidden'); refreshAll(); }
function showLogin() { appView.classList.add('hidden'); loginView.classList.remove('hidden'); }
async function checkSession() { try { const data = await api('/api/auth/me'); if (data.ok) showApp(data.username); } catch (_) { showLogin(); } }

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  setMessage(loginMessage, 'Checking credentials...');
  submitButton.disabled = true;
  try {
    const data = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username: $('#username').value.trim(), password: passwordInput.value }) });
    setMessage(loginMessage, 'Login successful. Opening panel...', 'success');
    setTimeout(() => showApp(data.username), 250);
  } catch (error) { setMessage(loginMessage, error.message || 'Cannot connect to the server.', 'error'); }
  finally { submitButton.disabled = false; }
});
logoutButton.addEventListener('click', async () => { await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => {}); showLogin(); setMessage(loginMessage, 'You have been logged out.', 'success'); });
togglePassword.addEventListener('click', () => { const visible = passwordInput.type === 'text'; passwordInput.type = visible ? 'password' : 'text'; togglePassword.textContent = visible ? 'Show' : 'Hide'; });

$$('.nav-item[data-page]').forEach((button) => button.addEventListener('click', () => switchPage(button.dataset.page)));
function switchPage(page) {
  state.page = page;
  state.editingCore = null;
  state.editorDraft = null;
  $$('.nav-item[data-page]').forEach((item) => item.classList.toggle('active', item.dataset.page === page));
  $$('.page').forEach((item) => item.classList.remove('active'));
  $(`#${page}Page`).classList.add('active');
  pageTitle.textContent = page === 'nodes' ? 'Nodes' : page === 'cores' ? 'Cores' : 'Dashboard';
  $('#openNodeModal').classList.toggle('hidden', page === 'cores' || page === 'coreEditor');
  $('#openCoreModal').classList.toggle('hidden', page !== 'cores');
}
function openCoreEditorPage(core) {
  state.page = 'coreEditor';
  state.editingCore = core;
  state.editorDraft = deepCopy(core);
  if (!Array.isArray(state.editorDraft.inbounds)) state.editorDraft.inbounds = [];
  if (!Array.isArray(state.editorDraft.balancers)) state.editorDraft.balancers = [];
  if (!Array.isArray(state.editorDraft.dependencies)) state.editorDraft.dependencies = [];
  $$('.nav-item[data-page]').forEach((item) => item.classList.remove('active'));
  $$('.page').forEach((item) => item.classList.remove('active'));
  $('#coreEditorPage').classList.add('active');
  pageTitle.textContent = `Edit Core: ${core.name || 'core'}`;
  $('#openNodeModal').classList.add('hidden');
  $('#openCoreModal').classList.add('hidden');
  bindCoreEditorHeader();
  switchCoreTab('inbounds');
  renderCoreEditor();
}

async function refreshAll() { await Promise.all([loadNodes(), loadCores()]); await loadSummary(); }
async function loadSummary() { try { const data = await api('/api/panel/summary'); $('#totalNodes').textContent = data.nodes_total ?? 0; $('#enabledNodes').textContent = data.nodes_enabled ?? 0; $('#totalCores').textContent = data.cores_total ?? state.cores.length; } catch (_) {} }
async function loadNodes() { try { const data = await api('/api/nodes'); state.nodes = data.nodes || []; renderNodes(); } catch (error) { console.error(error); } }
async function loadCores() { try { const data = await api('/api/cores'); state.cores = data.cores || []; state.inboundCatalog = data.inbound_catalog || []; renderCores(); } catch (error) { console.error(error); } }

function statusFor(node) { if (!node.enabled) return 'disabled'; const status = String(node.status || 'pending').toLowerCase(); return ['disabled', 'pending', 'running', 'error'].includes(status) && status !== 'disabled' ? status : 'pending'; }
function statusLabel(status) { return { disabled: 'Disabled', pending: 'Pending Check', running: 'Running', error: 'Error', ready: 'Ready', applied: 'Applied', draft: 'Draft' }[status] || 'Pending Check'; }
function statusDotClass(status) { if (status === 'disabled') return 'gray'; if (status === 'error') return 'red'; if (status === 'pending' || status === 'ready' || status === 'draft') return 'yellow'; return ''; }

function renderNodes() {
  const body = $('#nodesTableBody'); const empty = $('#nodesEmpty'); const wrap = $('#nodesTableWrap');
  body.innerHTML = ''; empty.classList.toggle('hidden', state.nodes.length > 0); wrap.classList.toggle('hidden', state.nodes.length === 0);
  for (const node of state.nodes) {
    const status = statusFor(node); const tr = document.createElement('tr');
    tr.innerHTML = `<td><span class="badge ${escapeHtml(status)}"><span class="status-dot ${statusDotClass(status)}"></span>${escapeHtml(statusLabel(status))}</span></td><td>${escapeHtml(node.name || '-')}</td><td>${escapeHtml(node.address || '-')}</td><td>${escapeHtml(node.node_port ?? '-')}</td><td>${escapeHtml(node.api_port ?? '-')}</td><td>${escapeHtml((node.connection_type || 'grpc').toUpperCase())}</td><td>${node.certificate ? 'Yes' : 'No'}</td><td>${node.enabled ? 'Yes' : 'No'}</td><td><div class="row-actions"><button class="mini-btn" data-check="${node.id}">Check</button><button class="mini-btn" data-edit="${node.id}">Edit</button><button class="mini-btn" data-delete="${node.id}">Delete</button></div></td>`;
    if (node.last_error) tr.title = node.last_error; body.appendChild(tr);
  }
  $$('[data-check]').forEach((button) => button.addEventListener('click', () => checkSavedNode(button.dataset.check, button)));
  $$('[data-edit]').forEach((button) => button.addEventListener('click', () => openNodeModal(state.nodes.find((node) => node.id === button.dataset.edit))));
  $$('[data-delete]').forEach((button) => button.addEventListener('click', () => deleteNode(button.dataset.delete)));
}

function setStatusPreview(status, message = '') { $('#nodeStatusText').textContent = statusLabel(status); $('#nodeStatusDot').classList.remove('gray','red','yellow'); const klass = statusDotClass(status); if (klass) $('#nodeStatusDot').classList.add(klass); if (message) setMessage(nodeMessage, message, status === 'running' ? 'success' : status === 'error' ? 'error' : ''); }
function updateStatusPreview() { if (!$('#nodeEnabled').checked) return setStatusPreview('disabled'); if (state.lastFormCheck) return setStatusPreview(state.lastFormCheck.ok ? 'running' : 'error'); setStatusPreview('pending'); }
function resetNodeForm() {
  nodeForm.reset(); state.editingNode = null; state.lastFormCheck = null; $('#nodeId').value = ''; $('#nodePort').value = '62050'; $('#apiPort').value = '62051'; $('#usageRatio').value = '1'; $('#connectionType').value = 'grpc'; $('#keepAliveValue').value = '60'; $('#keepAliveUnit').value = 'seconds'; $('#defaultTimeout').value = '10'; $('#internalTimeout').value = '15'; $('#nodeEnabled').checked = true; updateStatusPreview(); $('#deleteNodeButton').classList.add('hidden'); $('#nodeModalTitle').textContent = 'Create Node'; $('#nodeModalSubtitle').textContent = 'Add a node definition and check its control-plane API.'; setMessage(nodeMessage, '');
}
function openNodeModal(node = null) {
  resetNodeForm();
  if (node) {
    state.editingNode = node; $('#nodeId').value = node.id || ''; $('#nodeName').value = node.name || ''; $('#nodeAddress').value = node.address || ''; $('#nodePort').value = node.node_port || 62050; $('#apiPort').value = node.api_port || 62051; $('#apiKey').value = node.api_key || ''; $('#certificate').value = node.certificate || ''; $('#nodeEnabled').checked = Boolean(node.enabled); $('#usageRatio').value = node.usage_ratio ?? 1; $('#connectionType').value = node.connection_type || 'grpc'; $('#keepAliveValue').value = node.keep_alive_value || 60; $('#keepAliveUnit').value = node.keep_alive_unit || 'seconds'; $('#dataLimitGb').value = node.data_limit_gb ?? ''; $('#defaultTimeout').value = node.default_timeout || 10; $('#internalTimeout').value = node.internal_timeout || 15; $('#proxyUrl').value = node.proxy_url || ''; setStatusPreview(statusFor(node)); if (node.last_error) setMessage(nodeMessage, node.last_error, 'error'); $('#deleteNodeButton').classList.remove('hidden'); $('#nodeModalTitle').textContent = 'Edit Node'; $('#nodeModalSubtitle').textContent = node.name || 'Update node definition.';
  }
  nodeModal.classList.remove('hidden'); setTimeout(() => $('#nodeName').focus(), 50);
}
function closeNodeModal() { nodeModal.classList.add('hidden'); }
function nodePayload() { const dataLimit = $('#dataLimitGb').value.trim(); return { name: $('#nodeName').value.trim(), address: $('#nodeAddress').value.trim(), node_port: Number($('#nodePort').value || 62050), api_port: Number($('#apiPort').value || 62051), api_key: $('#apiKey').value.trim(), certificate: $('#certificate').value, enabled: $('#nodeEnabled').checked, usage_ratio: Number($('#usageRatio').value || 1), connection_type: $('#connectionType').value, keep_alive_value: Number($('#keepAliveValue').value || 60), keep_alive_unit: $('#keepAliveUnit').value, data_limit_gb: dataLimit ? Number(dataLimit) : null, default_timeout: Number($('#defaultTimeout').value || 10), internal_timeout: Number($('#internalTimeout').value || 15), proxy_url: $('#proxyUrl').value.trim() }; }
nodeForm.addEventListener('submit', async (event) => { event.preventDefault(); setMessage(nodeMessage, 'Saving node...'); try { const payload = nodePayload(); if (!payload.api_key) throw new Error('API Key is required. Generate or enter one.'); if (state.editingNode) await api(`/api/nodes/${encodeURIComponent(state.editingNode.id)}`, { method: 'PUT', body: JSON.stringify(payload) }); else await api('/api/nodes', { method: 'POST', body: JSON.stringify(payload) }); setMessage(nodeMessage, 'Node saved successfully.', 'success'); await refreshAll(); setTimeout(closeNodeModal, 250); } catch (error) { setMessage(nodeMessage, error.message || 'Cannot save node.', 'error'); } });
async function deleteNode(id) { if (!id || !confirm('Delete this node?')) return; try { await api(`/api/nodes/${encodeURIComponent(id)}`, { method: 'DELETE' }); await refreshAll(); closeNodeModal(); } catch (error) { alert(error.message || 'Cannot delete node.'); } }
async function checkSavedNode(id, button = null) { if (!id) return; const oldText = button ? button.textContent : ''; if (button) { button.disabled = true; button.textContent = 'Checking...'; } try { const data = await api(`/api/nodes/${encodeURIComponent(id)}/check`, { method: 'POST' }); await refreshAll(); if (!data.ok) alert(data.message || 'Node API is not reachable.'); } catch (error) { alert(error.message || 'Cannot check node.'); } finally { if (button) { button.disabled = false; button.textContent = oldText; } } }
async function checkFormNode() { setMessage(nodeMessage, 'Checking node API status...'); const button = $('#checkNodeStatus'); button.disabled = true; try { const payload = nodePayload(); if (!payload.name) payload.name = 'temporary-check'; if (!payload.address) throw new Error('Node Address is required for status check.'); if (!payload.api_key) throw new Error('API Key is required for status check.'); let data; if (state.editingNode && state.editingNode.id) { await api(`/api/nodes/${encodeURIComponent(state.editingNode.id)}`, { method: 'PUT', body: JSON.stringify(payload) }); data = await api(`/api/nodes/${encodeURIComponent(state.editingNode.id)}/check`, { method: 'POST' }); await refreshAll(); } else { data = await api('/api/nodes/check', { method: 'POST', body: JSON.stringify(payload) }); } state.lastFormCheck = data; if (data.ok) setStatusPreview('running', `Node API reachable through API Port ${data.using_api_port || payload.api_port}: ${data.url || ''}`.trim()); else setStatusPreview('error', data.message || 'Node API is not reachable.'); } catch (error) { state.lastFormCheck = { ok: false }; setStatusPreview('error', error.message || 'Cannot check node.'); } finally { button.disabled = false; } }
$('#generateApiKey').addEventListener('click', async () => { try { const data = await api('/api/nodes/api-key', { method: 'POST' }); $('#apiKey').value = data.api_key; } catch (_) { $('#apiKey').value = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`; } });

function renderCores() {
  const grid = $('#coresGrid'); const empty = $('#coresEmpty');
  grid.innerHTML = ''; empty.classList.toggle('hidden', state.cores.length > 0);
  for (const core of state.cores) {
    const status = core.enabled ? (core.status || 'ready') : 'disabled'; const card = document.createElement('article'); card.className = 'core-card';
    const inboundCount = (core.inbounds || []).length; const balancerCount = (core.balancers || []).length; const depCount = (core.dependencies || []).length;
    card.innerHTML = `<div class="core-card-head"><span class="badge ${escapeHtml(status)}"><span class="status-dot ${statusDotClass(status)}"></span>${escapeHtml(statusLabel(status))}</span><div class="row-actions"><button class="mini-btn" data-open-core="${core.id}">Open</button><button class="mini-btn" data-preview-core="${core.id}">Preview</button><button class="mini-btn danger-mini" data-delete-core="${core.id}">Delete</button></div></div><h3>${escapeHtml(core.name || '-')}</h3><p>Node: <b>${escapeHtml(nodeName(core.node_id))}</b></p><div class="core-meta"><span>${inboundCount} inbounds</span><span>${balancerCount} balancers</span><span>${depCount} deps</span></div>`;
    card.addEventListener('dblclick', () => openCoreEditorPage(core));
    grid.appendChild(card);
  }
  $$('[data-open-core]').forEach((button) => button.addEventListener('click', () => openCoreEditorPage(coreById(button.dataset.openCore))));
  $$('[data-delete-core]').forEach((button) => button.addEventListener('click', () => deleteCore(button.dataset.deleteCore)));
  $$('[data-preview-core]').forEach((button) => button.addEventListener('click', () => previewCore(button.dataset.previewCore)));
}
function fillNodeSelect(select, value = '') { select.innerHTML = state.nodes.map(node => `<option value="${escapeHtml(node.id)}">${escapeHtml(node.name)} — ${escapeHtml(node.address)}:${escapeHtml(node.api_port || 62051)}</option>`).join('') || '<option value="">No nodes available</option>'; select.value = value || (state.nodes[0] || {}).id || ''; }
function resetCoreCreateForm() { coreCreateForm.reset(); fillNodeSelect($('#createCoreNode')); $('#createCoreEnabled').checked = true; setMessage(coreCreateMessage, ''); }
function openCoreCreateModal() { resetCoreCreateForm(); coreCreateModal.classList.remove('hidden'); setTimeout(() => $('#createCoreName').focus(), 50); }
function closeCoreCreateModal() { coreCreateModal.classList.add('hidden'); }
coreCreateForm.addEventListener('submit', async (event) => { event.preventDefault(); setMessage(coreCreateMessage, 'Creating core...'); try { const payload = { name: $('#createCoreName').value.trim(), node_id: $('#createCoreNode').value, enabled: $('#createCoreEnabled').checked, inbounds: [], balancers: [], dependencies: [] }; if (!payload.name) throw new Error('Core name is required.'); if (!payload.node_id) throw new Error('Select a node first.'); const data = await api('/api/cores', { method: 'POST', body: JSON.stringify(payload) }); setMessage(coreCreateMessage, 'Core created. Opening editor...', 'success'); await refreshAll(); setTimeout(() => { closeCoreCreateModal(); openCoreEditorPage(data.core); }, 250); } catch (error) { setMessage(coreCreateMessage, error.message || 'Cannot create core.', 'error'); } });
async function deleteCore(id) { if (!id || !confirm('Delete this core?')) return; try { await api(`/api/cores/${encodeURIComponent(id)}`, { method: 'DELETE' }); await refreshAll(); if (state.editingCore && state.editingCore.id === id) switchPage('cores'); } catch (error) { alert(error.message || 'Cannot delete core.'); } }
async function previewCore(id) { try { const data = await api(`/api/cores/${encodeURIComponent(id)}/preview`); const text = JSON.stringify(data.node_config_preview, null, 2); const w = window.open('', '_blank'); if (w) { w.document.write(`<pre style="background:#0b0e14;color:#eef3ff;padding:24px;white-space:pre-wrap;font-family:monospace">${escapeHtml(text)}</pre>`); w.document.close(); } else { alert(text.slice(0, 4000)); } } catch (error) { alert(error.message || 'Cannot preview core.'); } }

function bindCoreEditorHeader() {
  if (!state.editorDraft) return;
  $('#editorCoreName').value = state.editorDraft.name || '';
  fillNodeSelect($('#editorCoreNode'), state.editorDraft.node_id || '');
  $('#editorCoreEnabled').checked = Boolean(state.editorDraft.enabled !== false);
  setMessage(coreEditorMessage, '');
}
function syncEditorHeaderToDraft() {
  if (!state.editorDraft) return;
  state.editorDraft.name = $('#editorCoreName').value.trim();
  state.editorDraft.node_id = $('#editorCoreNode').value;
  state.editorDraft.enabled = $('#editorCoreEnabled').checked;
}
function switchCoreTab(tab) {
  state.currentCoreTab = tab;
  $$('.tab').forEach(btn => btn.classList.toggle('active', btn.dataset.coreTab === tab));
  $$('.tab-panel').forEach(panel => panel.classList.remove('active'));
  const target = { inbounds: '#tabInbounds', routing: '#tabRouting', balancers: '#tabBalancers', dependencies: '#tabDependencies', preview: '#tabPreview' }[tab];
  $(target).classList.add('active');
  if (tab === 'preview') renderPreviewBox();
}
function renderCoreEditor() {
  if (!state.editorDraft) return;
  renderInboundEditor();
  renderRoutingEditor();
  renderBalancerEditor();
  renderDependencyEditor();
}
function defaultInbound() { return { name: `inbound-${(state.editorDraft.inbounds || []).length + 1}`, bind_ip: '0.0.0.0', public_host: '', port_mode: 'fixed', fixed_ports: [], random_count: 1, target_type: 'static', target_host: '127.0.0.1', target_port: 80, target_balancer: '', certificate: '', enabled: true, notes: '' }; }
function defaultBalancer() { return { alias: `balancer-${(state.editorDraft.balancers || []).length + 1}`, strategy: 'round_robin', endpoints: [], enabled: true, notes: '' }; }
function defaultEndpoint() { return { type: 'static', host: '127.0.0.1', port: 80, node_id: '', core_id: '', inbound_name: '', weight: 1, certificate: '', enabled: true, notes: '' }; }
function defaultDependency() { return { type: 'core', ref_id: '', required: true, notes: '' }; }
function portsToText(ports) { return Array.isArray(ports) ? ports.join(',') : String(ports || ''); }
function parsePorts(text) { return String(text || '').split(',').map(p => Number(p.trim())).filter(p => Number.isInteger(p) && p >= 1 && p <= 65535); }
function currentBalancerAliases() { return (state.editorDraft?.balancers || []).map(b => b.alias).filter(Boolean); }

function renderInboundEditor() {
  const list = $('#inboundEditorList'); list.innerHTML = '';
  if (!state.editorDraft.inbounds.length) { list.innerHTML = '<div class="empty-state">No inbounds yet. Add one to define listener ports.</div>'; return; }
  state.editorDraft.inbounds.forEach((inbound, index) => {
    const card = document.createElement('article'); card.className = 'builder-card inbound-card';
    const isRandom = inbound.port_mode === 'random';
    card.innerHTML = `<div class="builder-card-head"><strong>${escapeHtml(inbound.name || `Inbound ${index + 1}`)}</strong><button class="mini-btn danger-mini" type="button" data-remove-inbound="${index}">Remove</button></div><div class="advanced-grid"><label class="field"><span>Name</span><input data-in-index="${index}" data-field="name" value="${escapeHtml(inbound.name || '')}" placeholder="vless-us-000" /></label><label class="field"><span>Bind IP</span><input data-in-index="${index}" data-field="bind_ip" value="${escapeHtml(inbound.bind_ip || '0.0.0.0')}" placeholder="0.0.0.0" /></label><label class="field"><span>Port Mode</span><select data-in-index="${index}" data-field="port_mode"><option value="fixed">Fixed ports</option><option value="random">Random ports</option></select></label><label class="field ${isRandom ? 'hidden' : ''}" data-port-fixed><span>Ports</span><input data-in-index="${index}" data-field="fixed_ports_text" value="${escapeHtml(portsToText(inbound.fixed_ports))}" placeholder="31648,30943,31042" /><small>Comma separated ports.</small></label><label class="field ${isRandom ? '' : 'hidden'}" data-port-random><span>Random Port Count</span><input data-in-index="${index}" data-field="random_count" type="number" min="1" max="4096" value="${escapeHtml(inbound.random_count || 1)}" /><small>The runtime will allocate this many free ports.</small></label><label class="field wide"><span>Inbound TLS Certificate</span><textarea data-in-index="${index}" data-field="certificate" placeholder="Optional public certificate for this inbound">${escapeHtml(inbound.certificate || '')}</textarea></label><label class="checkline"><input data-in-index="${index}" data-field="enabled" type="checkbox" ${inbound.enabled === false ? '' : 'checked'} /> Enabled</label></div>`;
    card.querySelector('[data-field="port_mode"]').value = inbound.port_mode || 'fixed';
    list.appendChild(card);
  });
  $$('[data-remove-inbound]').forEach(btn => btn.addEventListener('click', () => { state.editorDraft.inbounds.splice(Number(btn.dataset.removeInbound), 1); renderCoreEditor(); }));
  $$('#inboundEditorList [data-field]').forEach(bindInboundField);
}
function bindInboundField(el) {
  const index = Number(el.dataset.inIndex); const field = el.dataset.field;
  el.addEventListener(field === 'enabled' ? 'change' : 'input', () => {
    const inbound = state.editorDraft.inbounds[index]; if (!inbound) return;
    if (field === 'enabled') inbound.enabled = el.checked;
    else if (field === 'fixed_ports_text') inbound.fixed_ports = parsePorts(el.value);
    else if (field === 'random_count') inbound.random_count = Math.max(1, Number(el.value || 1));
    else inbound[field] = el.value;
    if (field === 'port_mode') { renderInboundEditor(); renderRoutingEditor(); }
    if (field === 'name') { renderRoutingEditor(); updateBalancerEndpointSelectors(); }
  });
  el.addEventListener('change', () => { if (field === 'fixed_ports_text') state.editorDraft.inbounds[index].fixed_ports = parsePorts(el.value); });
}
function renderRoutingEditor() {
  const list = $('#routingEditorList'); list.innerHTML = '';
  if (!state.editorDraft.inbounds.length) { list.innerHTML = '<div class="empty-state">Add an inbound first, then configure routing here.</div>'; return; }
  state.editorDraft.inbounds.forEach((inbound, index) => {
    const aliases = currentBalancerAliases(); const isBalancer = inbound.target_type === 'balancer';
    const card = document.createElement('article'); card.className = 'builder-card route-card';
    card.innerHTML = `<div class="builder-card-head"><strong>${escapeHtml(inbound.name || `Inbound ${index + 1}`)} Routing</strong><span class="muted-text">${escapeHtml(inbound.port_mode === 'random' ? `${inbound.random_count || 1} random port(s)` : portsToText(inbound.fixed_ports) || 'no ports')}</span></div><div class="advanced-grid"><label class="field"><span>Route Target</span><select data-route-index="${index}" data-route-field="target_type"><option value="static">Direct Static IP:Port</option><option value="balancer">Balancer Alias</option></select></label><label class="field ${isBalancer ? 'hidden' : ''}" data-route-static><span>Target Host</span><input data-route-index="${index}" data-route-field="target_host" value="${escapeHtml(inbound.target_host || '127.0.0.1')}" /></label><label class="field ${isBalancer ? 'hidden' : ''}" data-route-static><span>Target Port</span><input data-route-index="${index}" data-route-field="target_port" type="number" min="1" max="65535" value="${escapeHtml(inbound.target_port || 80)}" /></label><label class="field wide ${isBalancer ? '' : 'hidden'}" data-route-balancer><span>Balancer</span><select data-route-index="${index}" data-route-field="target_balancer">${aliases.map(alias => `<option value="${escapeHtml(alias)}">${escapeHtml(alias)}</option>`).join('') || '<option value="">No balancer yet</option>'}</select><small>Create balancers in the Balancers tab.</small></label><label class="field wide"><span>Routing Notes</span><input data-route-index="${index}" data-route-field="notes" value="${escapeHtml(inbound.notes || '')}" placeholder="Optional note" /></label></div>`;
    card.querySelector('[data-route-field="target_type"]').value = inbound.target_type || 'static';
    const balSelect = card.querySelector('[data-route-field="target_balancer"]'); if (balSelect) balSelect.value = inbound.target_balancer || (aliases[0] || '');
    list.appendChild(card);
  });
  $$('#routingEditorList [data-route-field]').forEach((el) => {
    const index = Number(el.dataset.routeIndex); const field = el.dataset.routeField;
    el.addEventListener('input', () => applyRouteField(index, field, el));
    el.addEventListener('change', () => { applyRouteField(index, field, el); if (field === 'target_type') renderRoutingEditor(); });
  });
}
function applyRouteField(index, field, el) {
  const inbound = state.editorDraft.inbounds[index]; if (!inbound) return;
  if (field === 'target_port') inbound.target_port = Number(el.value || 80);
  else inbound[field] = el.value;
}

function renderBalancerEditor() {
  const list = $('#balancerEditorList'); list.innerHTML = '';
  if (!state.editorDraft.balancers.length) { list.innerHTML = '<div class="empty-state">No balancers yet. Create a balancer alias when an inbound should distribute traffic.</div>'; return; }
  state.editorDraft.balancers.forEach((balancer, index) => {
    const card = document.createElement('article'); card.className = 'builder-card balancer-card';
    card.innerHTML = `<div class="builder-card-head"><strong>${escapeHtml(balancer.alias || `Balancer ${index + 1}`)}</strong><button class="mini-btn danger-mini" type="button" data-remove-balancer="${index}">Remove</button></div><div class="advanced-grid"><label class="field"><span>Alias</span><input data-bal-index="${index}" data-bal-field="alias" value="${escapeHtml(balancer.alias || '')}" /></label><label class="field"><span>Strategy</span><select data-bal-index="${index}" data-bal-field="strategy"><option value="round_robin">Round Robin</option><option value="random">Random</option><option value="failover">Failover</option><option value="least_connections">Least Connections</option></select></label><label class="checkline"><input data-bal-index="${index}" data-bal-field="enabled" type="checkbox" ${balancer.enabled === false ? '' : 'checked'} /> Enabled</label><label class="field wide"><span>Notes</span><input data-bal-index="${index}" data-bal-field="notes" value="${escapeHtml(balancer.notes || '')}" /></label><div class="wide endpoint-list" id="endpointList_${index}"></div><button class="ghost-btn wide" type="button" data-add-endpoint="${index}">+ Add Endpoint</button></div>`;
    card.querySelector('[data-bal-field="strategy"]').value = balancer.strategy || 'round_robin';
    list.appendChild(card);
    renderEndpointList(index);
  });
  $$('[data-remove-balancer]').forEach(btn => btn.addEventListener('click', () => { state.editorDraft.balancers.splice(Number(btn.dataset.removeBalancer), 1); renderCoreEditor(); }));
  $$('[data-add-endpoint]').forEach(btn => btn.addEventListener('click', () => { const balancer = state.editorDraft.balancers[Number(btn.dataset.addEndpoint)]; balancer.endpoints = balancer.endpoints || []; balancer.endpoints.push(defaultEndpoint()); renderBalancerEditor(); }));
  $$('#balancerEditorList [data-bal-field]').forEach((el) => {
    const index = Number(el.dataset.balIndex); const field = el.dataset.balField;
    el.addEventListener(field === 'enabled' ? 'change' : 'input', () => {
      const bal = state.editorDraft.balancers[index]; if (!bal) return;
      if (field === 'enabled') bal.enabled = el.checked; else bal[field] = el.value;
      if (field === 'alias') renderRoutingEditor();
    });
  });
}
function renderEndpointList(balancerIndex) {
  const balancer = state.editorDraft.balancers[balancerIndex];
  const list = $(`#endpointList_${balancerIndex}`); if (!list) return;
  list.innerHTML = '';
  const endpoints = balancer.endpoints || [];
  if (!endpoints.length) { list.innerHTML = '<div class="empty-state small-empty">No endpoints. Add static targets or choose an inbound from a saved node/core.</div>'; return; }
  endpoints.forEach((endpoint, endpointIndex) => {
    const isNodeInbound = endpoint.type === 'node_inbound';
    const card = document.createElement('div'); card.className = 'endpoint-card';
    card.innerHTML = `<div class="endpoint-grid"><label class="field"><span>Type</span><select data-ep-bal="${balancerIndex}" data-ep-index="${endpointIndex}" data-ep-field="type"><option value="static">Static IP:Port</option><option value="node_inbound">Node Inbound</option></select></label><label class="field ${isNodeInbound ? 'hidden' : ''}" data-ep-static><span>Host</span><input data-ep-bal="${balancerIndex}" data-ep-index="${endpointIndex}" data-ep-field="host" value="${escapeHtml(endpoint.host || '127.0.0.1')}" /></label><label class="field ${isNodeInbound ? 'hidden' : ''}" data-ep-static><span>Port</span><input data-ep-bal="${balancerIndex}" data-ep-index="${endpointIndex}" data-ep-field="port" type="number" min="1" max="65535" value="${escapeHtml(endpoint.port || 80)}" /></label><label class="field ${isNodeInbound ? '' : 'hidden'}" data-ep-inbound><span>Node</span><select data-ep-bal="${balancerIndex}" data-ep-index="${endpointIndex}" data-ep-field="node_id"></select></label><label class="field ${isNodeInbound ? '' : 'hidden'}" data-ep-inbound><span>Inbound</span><select data-ep-bal="${balancerIndex}" data-ep-index="${endpointIndex}" data-ep-field="inbound_name"></select></label><label class="field"><span>Weight</span><input data-ep-bal="${balancerIndex}" data-ep-index="${endpointIndex}" data-ep-field="weight" type="number" min="0" step="0.1" value="${escapeHtml(endpoint.weight ?? 1)}" /></label><label class="field wide"><span>Target Certificate</span><textarea data-ep-bal="${balancerIndex}" data-ep-index="${endpointIndex}" data-ep-field="certificate" placeholder="Optional certificate for HTTPS target/inbound">${escapeHtml(endpoint.certificate || '')}</textarea></label><label class="checkline"><input data-ep-bal="${balancerIndex}" data-ep-index="${endpointIndex}" data-ep-field="enabled" type="checkbox" ${endpoint.enabled === false ? '' : 'checked'} /> Enabled</label><button class="mini-btn danger-mini" type="button" data-remove-endpoint="${balancerIndex}:${endpointIndex}">Remove endpoint</button></div>`;
    card.querySelector('[data-ep-field="type"]').value = endpoint.type || 'static';
    list.appendChild(card);
    fillEndpointNodeSelect(card.querySelector('[data-ep-field="node_id"]'), endpoint.node_id || '');
    fillEndpointInboundSelect(card.querySelector('[data-ep-field="inbound_name"]'), endpoint.node_id || '', endpoint.inbound_name || '');
  });
  $$('[data-remove-endpoint]').forEach(btn => btn.addEventListener('click', () => { const [b, e] = btn.dataset.removeEndpoint.split(':').map(Number); state.editorDraft.balancers[b].endpoints.splice(e, 1); renderBalancerEditor(); }));
  $$('#balancerEditorList [data-ep-field]').forEach((el) => {
    const balIndex = Number(el.dataset.epBal); const epIndex = Number(el.dataset.epIndex); const field = el.dataset.epField;
    const handler = () => { const ep = state.editorDraft.balancers[balIndex]?.endpoints?.[epIndex]; if (!ep) return; if (field === 'enabled') ep.enabled = el.checked; else if (field === 'port' || field === 'weight') ep[field] = Number(el.value || (field === 'port' ? 80 : 1)); else ep[field] = el.value; if (field === 'node_id') { ep.inbound_name = ''; renderBalancerEditor(); } if (field === 'type') renderBalancerEditor(); };
    el.addEventListener(field === 'enabled' ? 'change' : 'input', handler);
    el.addEventListener('change', handler);
  });
}
function fillEndpointNodeSelect(select, value = '') { if (!select) return; select.innerHTML = state.nodes.map(node => `<option value="${escapeHtml(node.id)}">${escapeHtml(node.name)}</option>`).join('') || '<option value="">No nodes</option>'; select.value = value || (state.nodes[0] || {}).id || ''; }
function fillEndpointInboundSelect(select, nodeId, value = '') { if (!select) return; const items = state.inboundCatalog.filter(item => !nodeId || item.node_id === nodeId); select.innerHTML = items.map(item => `<option value="${escapeHtml(item.inbound_name)}">${escapeHtml(item.core_name)} / ${escapeHtml(item.inbound_name)}</option>`).join('') || '<option value="">No saved inbounds</option>'; select.value = value || (items[0] || {}).inbound_name || ''; }
function updateBalancerEndpointSelectors() { renderBalancerEditor(); }

function renderDependencyEditor() {
  const list = $('#dependencyEditorList'); list.innerHTML = '';
  const deps = state.editorDraft.dependencies || [];
  if (!deps.length) { list.innerHTML = '<div class="empty-state">No dependencies. Add them only when an apply/deploy step must wait for another node or core.</div>'; return; }
  deps.forEach((dep, index) => {
    const card = document.createElement('article'); card.className = 'builder-card dependency-card';
    const options = dependencyOptions(dep.type || 'core', dep.ref_id || '');
    card.innerHTML = `<div class="builder-card-head"><strong>Dependency</strong><button class="mini-btn danger-mini" type="button" data-remove-dep="${index}">Remove</button></div><div class="advanced-grid"><label class="field"><span>Type</span><select data-dep-index="${index}" data-dep-field="type"><option value="core">Core</option><option value="node">Node</option></select></label><label class="field"><span>Reference</span><select data-dep-index="${index}" data-dep-field="ref_id">${options}</select></label><label class="checkline"><input data-dep-index="${index}" data-dep-field="required" type="checkbox" ${dep.required === false ? '' : 'checked'} /> Required</label><label class="field wide"><span>Notes</span><input data-dep-index="${index}" data-dep-field="notes" value="${escapeHtml(dep.notes || '')}" /></label></div>`;
    card.querySelector('[data-dep-field="type"]').value = dep.type || 'core';
    list.appendChild(card);
  });
  $$('[data-remove-dep]').forEach(btn => btn.addEventListener('click', () => { state.editorDraft.dependencies.splice(Number(btn.dataset.removeDep), 1); renderDependencyEditor(); }));
  $$('#dependencyEditorList [data-dep-field]').forEach((el) => {
    const index = Number(el.dataset.depIndex); const field = el.dataset.depField;
    const handler = () => { const dep = state.editorDraft.dependencies[index]; if (!dep) return; if (field === 'required') dep.required = el.checked; else dep[field] = el.value; if (field === 'type') { dep.ref_id = ''; renderDependencyEditor(); } };
    el.addEventListener(field === 'required' ? 'change' : 'input', handler);
    el.addEventListener('change', handler);
  });
}
function dependencyOptions(type, selected) {
  const items = type === 'node' ? state.nodes.map(n => ({ id: n.id, label: n.name })) : state.cores.filter(c => !state.editorDraft || c.id !== state.editorDraft.id).map(c => ({ id: c.id, label: c.name }));
  if (!items.length) return '<option value="">No items available</option>';
  return items.map(item => `<option value="${escapeHtml(item.id)}" ${item.id === selected ? 'selected' : ''}>${escapeHtml(item.label)}</option>`).join('');
}

function renderPreviewBox() {
  if (!state.editorDraft) return;
  const preview = { version: 1, node_id: state.editorDraft.node_id, generated_by: 'panel-preview-draft', cores: [state.editorDraft] };
  $('#corePreviewBox').textContent = JSON.stringify(preview, null, 2);
}
async function refreshPreviewFromServer() {
  if (!state.editingCore?.id) return renderPreviewBox();
  try { const data = await api(`/api/cores/${encodeURIComponent(state.editingCore.id)}/preview`); $('#corePreviewBox').textContent = JSON.stringify(data.node_config_preview, null, 2); }
  catch (error) { $('#corePreviewBox').textContent = error.message || 'Cannot load preview.'; }
}
function collectEditorPayload() { syncEditorHeaderToDraft(); return { name: state.editorDraft.name, node_id: state.editorDraft.node_id, enabled: state.editorDraft.enabled, inbounds: state.editorDraft.inbounds || [], balancers: state.editorDraft.balancers || [], dependencies: state.editorDraft.dependencies || [] }; }
async function saveCoreEditor() {
  if (!state.editingCore?.id || !state.editorDraft) return;
  setMessage(coreEditorMessage, 'Saving core...');
  try {
    const payload = collectEditorPayload();
    if (!payload.name) throw new Error('Core name is required.');
    if (!payload.node_id) throw new Error('Select a node first.');
    const data = await api(`/api/cores/${encodeURIComponent(state.editingCore.id)}`, { method: 'PUT', body: JSON.stringify(payload) });
    state.editingCore = data.core; state.editorDraft = deepCopy(data.core);
    setMessage(coreEditorMessage, 'Core saved successfully.', 'success');
    await refreshAll();
    bindCoreEditorHeader();
    renderCoreEditor();
  } catch (error) { setMessage(coreEditorMessage, error.message || 'Cannot save core.', 'error'); }
}

$('#openNodeModal').addEventListener('click', () => openNodeModal());
$('#createNodeButton').addEventListener('click', () => openNodeModal());
$('#closeNodeModal').addEventListener('click', closeNodeModal);
$('#cancelNodeButton').addEventListener('click', closeNodeModal);
$('#deleteNodeButton').addEventListener('click', () => state.editingNode && deleteNode(state.editingNode.id));
$('#nodeEnabled').addEventListener('change', () => { state.lastFormCheck = null; updateStatusPreview(); });
$('#checkNodeStatus').addEventListener('click', checkFormNode);
nodeModal.addEventListener('click', (event) => { if (event.target === nodeModal) closeNodeModal(); });

$('#openCoreModal').addEventListener('click', openCoreCreateModal);
$('#createCoreButton').addEventListener('click', openCoreCreateModal);
$('#closeCoreCreateModal').addEventListener('click', closeCoreCreateModal);
$('#cancelCoreCreateButton').addEventListener('click', closeCoreCreateModal);
coreCreateModal.addEventListener('click', (event) => { if (event.target === coreCreateModal) closeCoreCreateModal(); });
$('#backToCores').addEventListener('click', () => switchPage('cores'));
$('#saveCoreEditor').addEventListener('click', saveCoreEditor);
$('#saveCoreEditorBottom').addEventListener('click', saveCoreEditor);
$('#addInboundButton').addEventListener('click', () => { state.editorDraft.inbounds.push(defaultInbound()); renderCoreEditor(); switchCoreTab('inbounds'); });
$('#addBalancerButton').addEventListener('click', () => { state.editorDraft.balancers.push(defaultBalancer()); renderCoreEditor(); switchCoreTab('balancers'); });
$('#addDependencyButton').addEventListener('click', () => { state.editorDraft.dependencies.push(defaultDependency()); renderDependencyEditor(); switchCoreTab('dependencies'); });
$('#refreshPreviewButton').addEventListener('click', refreshPreviewFromServer);
$$('.tab').forEach(btn => btn.addEventListener('click', () => switchCoreTab(btn.dataset.coreTab)));
$('#editorCoreName').addEventListener('input', syncEditorHeaderToDraft);
$('#editorCoreNode').addEventListener('change', syncEditorHeaderToDraft);
$('#editorCoreEnabled').addEventListener('change', syncEditorHeaderToDraft);
$('#refreshButton').addEventListener('click', refreshAll);

checkSession();

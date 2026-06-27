const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = { user: null, nodes: [], cores: [], inboundCatalog: [], page: 'dashboard', editingNode: null, editingCore: null, lastFormCheck: null };

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
const coreModal = $('#coreModal');
const coreForm = $('#coreForm');
const coreMessage = $('#coreMessage');

function setMessage(element, text, type = '') { element.textContent = text || ''; element.className = `message ${type}`.trim(); }
async function api(path, options = {}) {
  const response = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }, ...options });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || data.message || 'Request failed.');
  return data;
}
function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char])); }
function nodeName(id) { return (state.nodes.find(n => n.id === id) || {}).name || 'Unknown node'; }

function showApp(username) { state.user = username || 'admin'; adminName.textContent = state.user; loginView.classList.add('hidden'); appView.classList.remove('hidden'); refreshAll(); }
function showLogin() { appView.classList.add('hidden'); loginView.classList.remove('hidden'); }
async function checkSession() { try { const data = await api('/api/auth/me'); if (data.ok) showApp(data.username); } catch (_) { showLogin(); } }

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault(); setMessage(loginMessage, 'Checking credentials...'); submitButton.disabled = true;
  try { const data = await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ username: $('#username').value.trim(), password: passwordInput.value }) }); setMessage(loginMessage, 'Login successful. Opening panel...', 'success'); setTimeout(() => showApp(data.username), 250); }
  catch (error) { setMessage(loginMessage, error.message || 'Cannot connect to the server.', 'error'); }
  finally { submitButton.disabled = false; }
});
logoutButton.addEventListener('click', async () => { await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => {}); showLogin(); setMessage(loginMessage, 'You have been logged out.', 'success'); });
togglePassword.addEventListener('click', () => { const visible = passwordInput.type === 'text'; passwordInput.type = visible ? 'password' : 'text'; togglePassword.textContent = visible ? 'Show' : 'Hide'; });

$$('.nav-item[data-page]').forEach((button) => button.addEventListener('click', () => switchPage(button.dataset.page)));
function switchPage(page) {
  state.page = page;
  $$('.nav-item[data-page]').forEach((item) => item.classList.toggle('active', item.dataset.page === page));
  $$('.page').forEach((item) => item.classList.remove('active'));
  $(`#${page}Page`).classList.add('active');
  pageTitle.textContent = page === 'nodes' ? 'Nodes' : page === 'cores' ? 'Cores' : 'Dashboard';
  $('#openNodeModal').classList.toggle('hidden', page === 'cores');
  $('#openCoreModal').classList.toggle('hidden', page !== 'cores');
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
  const body = $('#coresTableBody'); const empty = $('#coresEmpty'); const wrap = $('#coresTableWrap');
  body.innerHTML = ''; empty.classList.toggle('hidden', state.cores.length > 0); wrap.classList.toggle('hidden', state.cores.length === 0);
  for (const core of state.cores) {
    const status = core.enabled ? (core.status || 'ready') : 'disabled'; const tr = document.createElement('tr');
    tr.innerHTML = `<td><span class="badge ${escapeHtml(status)}"><span class="status-dot ${statusDotClass(status)}"></span>${escapeHtml(statusLabel(status))}</span></td><td>${escapeHtml(core.name || '-')}</td><td>${escapeHtml(nodeName(core.node_id))}</td><td>${(core.inbounds || []).length}</td><td>${(core.balancers || []).length}</td><td>${core.enabled ? 'Yes' : 'No'}</td><td><div class="row-actions"><button class="mini-btn" data-preview-core="${core.id}">Preview</button><button class="mini-btn" data-edit-core="${core.id}">Edit</button><button class="mini-btn" data-delete-core="${core.id}">Delete</button></div></td>`;
    body.appendChild(tr);
  }
  $$('[data-edit-core]').forEach((button) => button.addEventListener('click', () => openCoreModal(state.cores.find((core) => core.id === button.dataset.editCore))));
  $$('[data-delete-core]').forEach((button) => button.addEventListener('click', () => deleteCore(button.dataset.deleteCore)));
  $$('[data-preview-core]').forEach((button) => button.addEventListener('click', () => previewCore(button.dataset.previewCore)));
}
function fillNodeSelect(select, value = '') { select.innerHTML = state.nodes.map(node => `<option value="${escapeHtml(node.id)}">${escapeHtml(node.name)} — ${escapeHtml(node.address)}:${escapeHtml(node.api_port || 62051)}</option>`).join('') || '<option value="">No nodes available</option>'; select.value = value || (state.nodes[0] || {}).id || ''; }
function resetCoreForm() { coreForm.reset(); state.editingCore = null; $('#coreId').value = ''; $('#coreName').value = ''; fillNodeSelect($('#coreNode')); $('#coreEnabled').checked = true; $('#inboundList').innerHTML = ''; $('#balancerList').innerHTML = ''; $('#deleteCoreButton').classList.add('hidden'); $('#coreModalTitle').textContent = 'Create Core'; $('#coreModalSubtitle').textContent = 'Choose a node, add inbounds and wire targets or balancers.'; setMessage(coreMessage, ''); $('#coreStatusText').textContent = 'Ready'; }
function openCoreModal(core = null) { resetCoreForm(); if (!state.nodes.length) setMessage(coreMessage, 'Create at least one node before creating a core.', 'error'); if (core) { state.editingCore = core; $('#coreId').value = core.id || ''; $('#coreName').value = core.name || ''; fillNodeSelect($('#coreNode'), core.node_id); $('#coreEnabled').checked = Boolean(core.enabled); (core.inbounds || []).forEach(addInbound); (core.balancers || []).forEach(addBalancer); $('#deleteCoreButton').classList.remove('hidden'); $('#coreModalTitle').textContent = 'Edit Core'; $('#coreModalSubtitle').textContent = core.name || 'Update core routing definition.'; } else { addInbound(); }
  updateBalancerOptions(); coreModal.classList.remove('hidden'); setTimeout(() => $('#coreName').focus(), 50); }
function closeCoreModal() { coreModal.classList.add('hidden'); }
function portsToText(ports) { return Array.isArray(ports) ? ports.join(',') : String(ports || ''); }

function addInbound(data = {}) {
  const el = document.createElement('article'); el.className = 'builder-card inbound-card';
  el.innerHTML = `<div class="builder-card-head"><strong>Inbound</strong><button class="mini-btn danger-mini" type="button" data-remove-card>Remove</button></div><div class="advanced-grid"><label class="field"><span>Alias / Name</span><input data-in="name" value="${escapeHtml(data.name || `inbound-${$$('.inbound-card').length + 1}`)}" required /></label><label class="field"><span>Bind IP</span><input data-in="bind_ip" value="${escapeHtml(data.bind_ip || '0.0.0.0')}" /></label><label class="field"><span>Port Mode</span><select data-in="port_mode"><option value="fixed">Fixed ports</option><option value="random">Random ports</option></select></label><label class="field"><span>Fixed Ports</span><input data-in="fixed_ports" placeholder="80,443,8443" value="${escapeHtml(portsToText(data.fixed_ports))}" /></label><label class="field"><span>Random Count</span><input data-in="random_count" type="number" min="1" value="${escapeHtml(data.random_count || 1)}" /></label><label class="field"><span>Target Type</span><select data-in="target_type"><option value="static">Static IP:Port</option><option value="balancer">Balancer Alias</option></select></label><label class="field"><span>Target Host</span><input data-in="target_host" value="${escapeHtml(data.target_host || '127.0.0.1')}" /></label><label class="field"><span>Target Port</span><input data-in="target_port" type="number" min="1" max="65535" value="${escapeHtml(data.target_port || 80)}" /></label><label class="field wide"><span>Target Balancer</span><select data-in="target_balancer"></select><small>Select a balancer alias from this core.</small></label><label class="field wide"><span>Inbound TLS Certificate</span><textarea data-in="certificate" placeholder="Optional public certificate for this inbound">${escapeHtml(data.certificate || '')}</textarea></label><label class="checkline"><input data-in="enabled" type="checkbox" ${data.enabled === false ? '' : 'checked'} /> Enabled</label></div>`;
  el.querySelector('[data-in="port_mode"]').value = data.port_mode || 'fixed'; el.querySelector('[data-in="target_type"]').value = data.target_type || 'static'; el.querySelector('[data-remove-card]').addEventListener('click', () => { el.remove(); updateBalancerOptions(); }); el.addEventListener('input', updateBalancerOptions); el.addEventListener('change', updateBalancerOptions); $('#inboundList').appendChild(el); updateBalancerOptions();
}
function addBalancer(data = {}) {
  const el = document.createElement('article'); el.className = 'builder-card balancer-card';
  el.innerHTML = `<div class="builder-card-head"><strong>Balancer</strong><button class="mini-btn danger-mini" type="button" data-remove-card>Remove</button></div><div class="advanced-grid"><label class="field"><span>Alias</span><input data-bal="alias" value="${escapeHtml(data.alias || `balancer-${$$('.balancer-card').length + 1}`)}" required /></label><label class="field"><span>Strategy</span><select data-bal="strategy"><option value="round_robin">Round Robin</option><option value="random">Random</option><option value="failover">Failover</option><option value="least_connections">Least Connections</option></select></label><label class="checkline"><input data-bal="enabled" type="checkbox" ${data.enabled === false ? '' : 'checked'} /> Enabled</label><div class="wide endpoint-list"></div><button class="ghost-btn wide" type="button" data-add-endpoint>+ Add Endpoint</button></div>`;
  el.querySelector('[data-bal="strategy"]').value = data.strategy || 'round_robin'; el.querySelector('[data-remove-card]').addEventListener('click', () => { el.remove(); updateBalancerOptions(); }); el.querySelector('[data-add-endpoint]').addEventListener('click', () => addEndpoint(el.querySelector('.endpoint-list'))); $('#balancerList').appendChild(el); (data.endpoints || [{}]).forEach(endpoint => addEndpoint(el.querySelector('.endpoint-list'), endpoint)); el.addEventListener('input', updateBalancerOptions); el.addEventListener('change', updateBalancerOptions); updateBalancerOptions();
}
function addEndpoint(list, data = {}) {
  const el = document.createElement('div'); el.className = 'endpoint-card';
  el.innerHTML = `<div class="endpoint-grid"><label class="field"><span>Type</span><select data-ep="type"><option value="static">Static IP:Port</option><option value="node_inbound">Node Inbound</option></select></label><label class="field"><span>Host</span><input data-ep="host" value="${escapeHtml(data.host || '127.0.0.1')}" /></label><label class="field"><span>Port</span><input data-ep="port" type="number" min="1" max="65535" value="${escapeHtml(data.port || 80)}" /></label><label class="field"><span>Node</span><select data-ep="node_id"></select></label><label class="field"><span>Inbound</span><select data-ep="inbound_name"></select></label><label class="field"><span>Weight</span><input data-ep="weight" type="number" min="0" step="0.1" value="${escapeHtml(data.weight ?? 1)}" /></label><label class="field wide"><span>Target Certificate</span><textarea data-ep="certificate" placeholder="Optional certificate for HTTPS target/inbound">${escapeHtml(data.certificate || '')}</textarea></label><label class="checkline"><input data-ep="enabled" type="checkbox" ${data.enabled === false ? '' : 'checked'} /> Enabled</label><button class="mini-btn danger-mini" type="button" data-remove-endpoint>Remove endpoint</button></div>`;
  el.querySelector('[data-ep="type"]').value = data.type || 'static'; fillNodeSelect(el.querySelector('[data-ep="node_id"]'), data.node_id || ''); fillInboundSelect(el.querySelector('[data-ep="inbound_name"]'), data.node_id || '', data.inbound_name || ''); el.querySelector('[data-ep="node_id"]').addEventListener('change', (e) => fillInboundSelect(el.querySelector('[data-ep="inbound_name"]'), e.target.value, '')); el.querySelector('[data-remove-endpoint]').addEventListener('click', () => el.remove()); list.appendChild(el);
}
function fillInboundSelect(select, nodeId, value = '') { const items = state.inboundCatalog.filter(item => !nodeId || item.node_id === nodeId); select.innerHTML = items.map(item => `<option value="${escapeHtml(item.inbound_name)}">${escapeHtml(item.core_name)} / ${escapeHtml(item.inbound_name)}</option>`).join('') || '<option value="">No saved inbounds</option>'; select.value = value || (items[0] || {}).inbound_name || ''; }
function currentBalancerAliases() { return $$('.balancer-card [data-bal="alias"]').map(input => input.value.trim()).filter(Boolean); }
function updateBalancerOptions() { const aliases = currentBalancerAliases(); $$('.inbound-card [data-in="target_balancer"]').forEach(select => { const old = select.value; select.innerHTML = aliases.map(alias => `<option value="${escapeHtml(alias)}">${escapeHtml(alias)}</option>`).join('') || '<option value="">No balancer yet</option>'; select.value = aliases.includes(old) ? old : (aliases[0] || ''); }); }
function parsePorts(text) { return String(text || '').split(',').map(p => Number(p.trim())).filter(p => Number.isInteger(p) && p >= 1 && p <= 65535); }
function collectCorePayload() { return { name: $('#coreName').value.trim(), node_id: $('#coreNode').value, enabled: $('#coreEnabled').checked, inbounds: $$('.inbound-card').map(card => ({ name: card.querySelector('[data-in="name"]').value.trim(), bind_ip: card.querySelector('[data-in="bind_ip"]').value.trim() || '0.0.0.0', public_host: '', port_mode: card.querySelector('[data-in="port_mode"]').value, fixed_ports: parsePorts(card.querySelector('[data-in="fixed_ports"]').value), random_count: Number(card.querySelector('[data-in="random_count"]').value || 1), target_type: card.querySelector('[data-in="target_type"]').value, target_host: card.querySelector('[data-in="target_host"]').value.trim() || '127.0.0.1', target_port: Number(card.querySelector('[data-in="target_port"]').value || 80), target_balancer: card.querySelector('[data-in="target_balancer"]').value || '', certificate: card.querySelector('[data-in="certificate"]').value || '', enabled: card.querySelector('[data-in="enabled"]').checked })), balancers: $$('.balancer-card').map(card => ({ alias: card.querySelector('[data-bal="alias"]').value.trim(), strategy: card.querySelector('[data-bal="strategy"]').value, enabled: card.querySelector('[data-bal="enabled"]').checked, endpoints: Array.from(card.querySelectorAll('.endpoint-card')).map(ep => ({ type: ep.querySelector('[data-ep="type"]').value, host: ep.querySelector('[data-ep="host"]').value.trim() || '127.0.0.1', port: Number(ep.querySelector('[data-ep="port"]').value || 80), node_id: ep.querySelector('[data-ep="node_id"]').value || '', inbound_name: ep.querySelector('[data-ep="inbound_name"]').value || '', weight: Number(ep.querySelector('[data-ep="weight"]').value || 1), certificate: ep.querySelector('[data-ep="certificate"]').value || '', enabled: ep.querySelector('[data-ep="enabled"]').checked })) })) }; }
coreForm.addEventListener('submit', async (event) => { event.preventDefault(); setMessage(coreMessage, 'Saving core...'); try { const payload = collectCorePayload(); if (!payload.node_id) throw new Error('Select a node first.'); if (!payload.inbounds.length) throw new Error('Add at least one inbound.'); if (state.editingCore) await api(`/api/cores/${encodeURIComponent(state.editingCore.id)}`, { method: 'PUT', body: JSON.stringify(payload) }); else await api('/api/cores', { method: 'POST', body: JSON.stringify(payload) }); setMessage(coreMessage, 'Core saved successfully.', 'success'); await refreshAll(); setTimeout(closeCoreModal, 250); } catch (error) { setMessage(coreMessage, error.message || 'Cannot save core.', 'error'); } });
async function deleteCore(id) { if (!id || !confirm('Delete this core?')) return; try { await api(`/api/cores/${encodeURIComponent(id)}`, { method: 'DELETE' }); await refreshAll(); closeCoreModal(); } catch (error) { alert(error.message || 'Cannot delete core.'); } }
async function previewCore(id) { try { const data = await api(`/api/cores/${encodeURIComponent(id)}/preview`); const text = JSON.stringify(data.node_config_preview, null, 2); const w = window.open('', '_blank'); if (w) { w.document.write(`<pre style="background:#0b0e14;color:#eef3ff;padding:24px;white-space:pre-wrap;font-family:monospace">${escapeHtml(text)}</pre>`); w.document.close(); } else { alert(text.slice(0, 4000)); } } catch (error) { alert(error.message || 'Cannot preview core.'); } }

$('#openNodeModal').addEventListener('click', () => openNodeModal());
$('#createNodeButton').addEventListener('click', () => openNodeModal());
$('#closeNodeModal').addEventListener('click', closeNodeModal);
$('#cancelNodeButton').addEventListener('click', closeNodeModal);
$('#deleteNodeButton').addEventListener('click', () => state.editingNode && deleteNode(state.editingNode.id));
$('#nodeEnabled').addEventListener('change', () => { state.lastFormCheck = null; updateStatusPreview(); });
$('#checkNodeStatus').addEventListener('click', checkFormNode);
nodeModal.addEventListener('click', (event) => { if (event.target === nodeModal) closeNodeModal(); });
$('#openCoreModal').addEventListener('click', () => openCoreModal());
$('#createCoreButton').addEventListener('click', () => openCoreModal());
$('#closeCoreModal').addEventListener('click', closeCoreModal);
$('#cancelCoreButton').addEventListener('click', closeCoreModal);
$('#deleteCoreButton').addEventListener('click', () => state.editingCore && deleteCore(state.editingCore.id));
$('#addInboundButton').addEventListener('click', () => addInbound());
$('#addBalancerButton').addEventListener('click', () => addBalancer());
coreModal.addEventListener('click', (event) => { if (event.target === coreModal) closeCoreModal(); });
$('#refreshButton').addEventListener('click', refreshAll);

checkSession();

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const state = { user: null, nodes: [], page: 'dashboard', editingNode: null };

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

function setMessage(element, text, type = '') {
  element.textContent = text || '';
  element.className = `message ${type}`.trim();
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || 'Request failed.');
  return data;
}

function showApp(username) {
  state.user = username || 'admin';
  adminName.textContent = state.user;
  loginView.classList.add('hidden');
  appView.classList.remove('hidden');
  loadSummary();
  loadNodes();
}

function showLogin() {
  appView.classList.add('hidden');
  loginView.classList.remove('hidden');
}

async function checkSession() {
  try {
    const data = await api('/api/auth/me');
    if (data.ok) showApp(data.username);
  } catch (_) {
    showLogin();
  }
}

loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  setMessage(loginMessage, 'Checking credentials...');
  submitButton.disabled = true;
  try {
    const data = await api('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username: $('#username').value.trim(), password: passwordInput.value }),
    });
    setMessage(loginMessage, 'Login successful. Opening panel...', 'success');
    setTimeout(() => showApp(data.username), 300);
  } catch (error) {
    setMessage(loginMessage, error.message || 'Cannot connect to the server.', 'error');
  } finally {
    submitButton.disabled = false;
  }
});

logoutButton.addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
  showLogin();
  setMessage(loginMessage, 'You have been logged out.', 'success');
});

togglePassword.addEventListener('click', () => {
  const visible = passwordInput.type === 'text';
  passwordInput.type = visible ? 'password' : 'text';
  togglePassword.textContent = visible ? 'Show' : 'Hide';
});

$$('.nav-item[data-page]').forEach((button) => {
  button.addEventListener('click', () => switchPage(button.dataset.page));
});

function switchPage(page) {
  state.page = page;
  $$('.nav-item[data-page]').forEach((item) => item.classList.toggle('active', item.dataset.page === page));
  $$('.page').forEach((item) => item.classList.remove('active'));
  $(`#${page}Page`).classList.add('active');
  pageTitle.textContent = page === 'nodes' ? 'Nodes' : 'Dashboard';
}

async function loadSummary() {
  try {
    const data = await api('/api/panel/summary');
    $('#totalNodes').textContent = data.nodes_total ?? 0;
    $('#enabledNodes').textContent = data.nodes_enabled ?? 0;
  } catch (_) {}
}

async function loadNodes() {
  try {
    const data = await api('/api/nodes');
    state.nodes = data.nodes || [];
    renderNodes();
    loadSummary();
  } catch (error) {
    console.error(error);
  }
}

function statusFor(node) {
  if (!node.enabled) return 'disabled';
  return node.status && node.status !== 'unknown' ? node.status : 'pending';
}

function renderNodes() {
  const body = $('#nodesTableBody');
  const empty = $('#nodesEmpty');
  const wrap = $('#nodesTableWrap');
  body.innerHTML = '';
  empty.classList.toggle('hidden', state.nodes.length > 0);
  wrap.classList.toggle('hidden', state.nodes.length === 0);
  for (const node of state.nodes) {
    const status = statusFor(node);
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="badge ${escapeHtml(status)}"><span class="status-dot ${statusDotClass(status)}"></span>${escapeHtml(statusLabel(status))}</span></td>
      <td>${escapeHtml(node.name || '-')}</td>
      <td>${escapeHtml(node.address || '-')}</td>
      <td>${escapeHtml(node.node_port ?? '-')}</td>
      <td>${escapeHtml(node.api_port ?? '-')}</td>
      <td>${escapeHtml((node.connection_type || 'grpc').toUpperCase())}</td>
      <td>${node.enabled ? 'Yes' : 'No'}</td>
      <td><div class="row-actions"><button class="mini-btn" data-edit="${node.id}">Edit</button><button class="mini-btn" data-delete="${node.id}">Delete</button></div></td>`;
    body.appendChild(tr);
  }
  $$('[data-edit]').forEach((button) => button.addEventListener('click', () => openNodeModal(state.nodes.find((node) => node.id === button.dataset.edit))));
  $$('[data-delete]').forEach((button) => button.addEventListener('click', () => deleteNode(button.dataset.delete)));
}

function statusLabel(status) {
  const labels = { disabled: 'Disabled', pending: 'Pending Check', running: 'Running', error: 'Error' };
  return labels[status] || 'Pending Check';
}

function statusDotClass(status) {
  if (status === 'disabled') return 'gray';
  if (status === 'error') return 'red';
  if (status === 'pending') return 'yellow';
  return '';
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[char]));
}

function updateStatusPreview() {
  const status = $('#nodeEnabled').checked ? 'pending' : 'disabled';
  $('#nodeStatusText').textContent = statusLabel(status);
  $('#nodeStatusDot').classList.remove('gray', 'red', 'yellow');
  const klass = statusDotClass(status);
  if (klass) $('#nodeStatusDot').classList.add(klass);
}

function resetNodeForm() {
  nodeForm.reset();
  state.editingNode = null;
  $('#nodeId').value = '';
  $('#nodePort').value = '62050';
  $('#apiPort').value = '62051';
  $('#usageRatio').value = '1';
  $('#connectionType').value = 'grpc';
  $('#keepAliveValue').value = '60';
  $('#keepAliveUnit').value = 'seconds';
  $('#defaultTimeout').value = '10';
  $('#internalTimeout').value = '15';
  $('#nodeEnabled').checked = false;
  updateStatusPreview();
  $('#deleteNodeButton').classList.add('hidden');
  $('#nodeModalTitle').textContent = 'Create Node';
  $('#nodeModalSubtitle').textContent = 'Add a node definition to the panel.';
  setMessage(nodeMessage, '');
}

function openNodeModal(node = null) {
  resetNodeForm();
  if (node) {
    state.editingNode = node;
    $('#nodeId').value = node.id || '';
    $('#nodeName').value = node.name || '';
    $('#nodeAddress').value = node.address || '';
    $('#nodePort').value = node.node_port || 62050;
    $('#apiKey').value = node.api_key || '';
    $('#certificate').value = node.certificate || '';
    $('#nodeEnabled').checked = Boolean(node.enabled);
    $('#usageRatio').value = node.usage_ratio ?? 1;
    $('#apiPort').value = node.api_port || 62051;
    $('#connectionType').value = node.connection_type || 'grpc';
    $('#keepAliveValue').value = node.keep_alive_value || 60;
    $('#keepAliveUnit').value = node.keep_alive_unit || 'seconds';
    $('#dataLimitGb').value = node.data_limit_gb ?? '';
    $('#defaultTimeout').value = node.default_timeout || 10;
    $('#internalTimeout').value = node.internal_timeout || 15;
    $('#proxyUrl').value = node.proxy_url || '';
    updateStatusPreview();
    $('#deleteNodeButton').classList.remove('hidden');
    $('#nodeModalTitle').textContent = 'Edit Node';
    $('#nodeModalSubtitle').textContent = node.name || 'Update node definition.';
  }
  nodeModal.classList.remove('hidden');
  setTimeout(() => $('#nodeName').focus(), 50);
}

function closeNodeModal() { nodeModal.classList.add('hidden'); }

function nodePayload() {
  const dataLimit = $('#dataLimitGb').value.trim();
  return {
    name: $('#nodeName').value.trim(),
    address: $('#nodeAddress').value.trim(),
    node_port: Number($('#nodePort').value || 62050),
    api_key: $('#apiKey').value.trim(),
    certificate: $('#certificate').value,
    enabled: $('#nodeEnabled').checked,
    usage_ratio: Number($('#usageRatio').value || 1),
    api_port: Number($('#apiPort').value || 62051),
    connection_type: $('#connectionType').value,
    keep_alive_value: Number($('#keepAliveValue').value || 60),
    keep_alive_unit: $('#keepAliveUnit').value,
    data_limit_gb: dataLimit ? Number(dataLimit) : null,
    default_timeout: Number($('#defaultTimeout').value || 10),
    internal_timeout: Number($('#internalTimeout').value || 15),
    proxy_url: $('#proxyUrl').value.trim(),
  };
}

nodeForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  setMessage(nodeMessage, 'Saving node...');
  try {
    const payload = nodePayload();
    if (!payload.api_key) throw new Error('API Key is required. Generate or enter one.');
    if (state.editingNode) {
      await api(`/api/nodes/${encodeURIComponent(state.editingNode.id)}`, { method: 'PUT', body: JSON.stringify(payload) });
    } else {
      await api('/api/nodes', { method: 'POST', body: JSON.stringify(payload) });
    }
    setMessage(nodeMessage, 'Node saved successfully.', 'success');
    await loadNodes();
    setTimeout(closeNodeModal, 300);
  } catch (error) {
    setMessage(nodeMessage, error.message || 'Cannot save node.', 'error');
  }
});

async function deleteNode(id) {
  if (!id || !confirm('Delete this node?')) return;
  try {
    await api(`/api/nodes/${encodeURIComponent(id)}`, { method: 'DELETE' });
    await loadNodes();
    closeNodeModal();
  } catch (error) {
    alert(error.message || 'Cannot delete node.');
  }
}

$('#generateApiKey').addEventListener('click', async () => {
  try {
    const data = await api('/api/nodes/api-key', { method: 'POST' });
    $('#apiKey').value = data.api_key;
  } catch (_) {
    $('#apiKey').value = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
});

$('#openNodeModal').addEventListener('click', () => openNodeModal());
$('#createNodeButton').addEventListener('click', () => openNodeModal());
$('#closeNodeModal').addEventListener('click', closeNodeModal);
$('#cancelNodeButton').addEventListener('click', closeNodeModal);
$('#deleteNodeButton').addEventListener('click', () => state.editingNode && deleteNode(state.editingNode.id));
$('#refreshButton').addEventListener('click', () => { loadSummary(); loadNodes(); });
$('#nodeEnabled').addEventListener('change', updateStatusPreview);
nodeModal.addEventListener('click', (event) => { if (event.target === nodeModal) closeNodeModal(); });

checkSession();

const loginCard = document.querySelector('.login-card');
const brandCard = document.querySelector('.brand-card');
const dashboard = document.querySelector('#dashboard');
const form = document.querySelector('#loginForm');
const message = document.querySelector('#message');
const submitButton = document.querySelector('#submitButton');
const adminName = document.querySelector('#adminName');
const logoutButton = document.querySelector('#logoutButton');
const togglePassword = document.querySelector('#togglePassword');
const passwordInput = document.querySelector('#password');

function setMessage(text, type = '') {
  message.textContent = text || '';
  message.className = `message ${type}`.trim();
}

function showDashboard(username) {
  adminName.textContent = username || 'admin';
  loginCard.classList.add('hidden');
  brandCard.classList.add('hidden');
  dashboard.classList.remove('hidden');
}

function showLogin() {
  dashboard.classList.add('hidden');
  loginCard.classList.remove('hidden');
  brandCard.classList.remove('hidden');
}

async function checkSession() {
  try {
    const response = await fetch('/api/auth/me', { credentials: 'same-origin' });
    if (!response.ok) return;
    const data = await response.json();
    if (data.ok) showDashboard(data.username);
  } catch (_) {
    // keep login visible
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  setMessage('در حال بررسی اطلاعات ورود...', '');
  submitButton.disabled = true;

  const payload = {
    username: document.querySelector('#username').value.trim(),
    password: passwordInput.value,
  };

  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || 'ورود ناموفق بود.');
    }

    setMessage('ورود موفق بود. در حال باز کردن پنل...', 'success');
    setTimeout(() => showDashboard(data.username), 350);
  } catch (error) {
    setMessage(error.message || 'خطا در اتصال به سرور.', 'error');
  } finally {
    submitButton.disabled = false;
  }
});

logoutButton.addEventListener('click', async () => {
  await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' }).catch(() => {});
  showLogin();
  setMessage('از پنل خارج شدی.', 'success');
});

togglePassword.addEventListener('click', () => {
  const visible = passwordInput.type === 'text';
  passwordInput.type = visible ? 'password' : 'text';
  togglePassword.textContent = visible ? 'نمایش' : 'مخفی';
});

checkSession();

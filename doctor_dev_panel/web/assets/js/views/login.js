import { escapeHtml } from "../core/utils.js";

export function renderLogin(error = "") {
  return `<main class="login-shell">
    <form id="loginForm" class="login-card">
      <div class="login-mark"><div class="logo-box">DD</div><div><h1>Doctor Dev</h1><p>Distributed routing control plane</p></div></div>
      ${error ? `<div class="notice bad">${escapeHtml(error)}</div>` : ""}
      <div class="login-form">
        <label class="field"><span>Username</span><input class="input" name="username" autocomplete="username" required maxlength="80" placeholder="admin"></label>
        <label class="field"><span>Password</span><input class="input" name="password" type="password" autocomplete="current-password" required maxlength="256" placeholder="admin12345"></label>
        <button class="btn primary" type="submit">Enter Panel</button>
      </div>
    </form>
  </main>`;
}

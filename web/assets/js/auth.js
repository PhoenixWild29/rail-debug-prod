// auth.js — JWT localStorage helpers used by dashboard.html and login flows

const AUTH_KEY = 'rd_token';

function getToken() {
  return localStorage.getItem(AUTH_KEY);
}

function setToken(token) {
  localStorage.setItem(AUTH_KEY, token);
}

function removeToken() {
  localStorage.removeItem(AUTH_KEY);
}

function getAuthHeaders() {
  const token = getToken();
  return token ? { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };
}

function parseJwt(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

function isLoggedIn() {
  const token = getToken();
  if (!token) return false;
  const payload = parseJwt(token);
  if (!payload || !payload.exp) return false;
  return payload.exp * 1000 > Date.now();
}

function logout() {
  removeToken();
  window.location.href = '/';
}

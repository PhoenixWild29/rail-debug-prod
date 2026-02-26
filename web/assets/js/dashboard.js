// dashboard.js — data fetch + render for dashboard.html

const TIER_LABELS = { free: 'Free', dev: 'Dev — $19/mo', team: 'Team — $99/mo' };
const TIER_COLORS = { free: '#8b949e', dev: '#58a6ff', team: '#00ff88' };
const MONTHLY_LIMITS = { free: 50, dev: 2000, team: null };

async function loadDashboard() {
  const res = await fetch('/api/auth/me', { headers: getAuthHeaders() });
  if (res.status === 401) { logout(); return; }
  if (!res.ok) { showError('Failed to load profile.'); return; }
  const user = await res.json();
  renderDashboard(user);
}

function renderDashboard(user) {
  document.getElementById('loading').style.display = 'none';
  document.getElementById('dash-content').style.display = 'block';

  // Account
  document.getElementById('user-email').textContent = user.email;
  const tierEl = document.getElementById('user-tier');
  tierEl.textContent = TIER_LABELS[user.tier] || user.tier;
  tierEl.style.color = TIER_COLORS[user.tier] || '#8b949e';
  const joinDate = user.created_at ? new Date(user.created_at).toLocaleDateString() : '—';
  document.getElementById('user-joined').textContent = joinDate;

  // Usage
  const monthly = user.monthly_usage || 0;
  const limit = MONTHLY_LIMITS[user.tier];
  const limitText = limit ? `${monthly} / ${limit}` : `${monthly} / unlimited`;
  document.getElementById('usage-count').textContent = limitText;
  if (limit) {
    const pct = Math.min((monthly / limit) * 100, 100);
    document.getElementById('usage-bar').style.width = `${pct}%`;
    document.getElementById('usage-bar').style.background = pct > 80 ? '#f85149' : '#00ff88';
  } else {
    document.getElementById('usage-bar').style.width = '10%';
  }

  // API Key
  const key = user.api_key || '';
  document.getElementById('api-key-display').textContent = key ? key.slice(0, 8) + '••••••••••••••••' + key.slice(-4) : '—';
  window._fullApiKey = key;

  // Billing
  const subStatus = user.subscription_status || 'inactive';
  document.getElementById('billing-status').textContent = subStatus.charAt(0).toUpperCase() + subStatus.slice(1);
  if (user.billing_period_end) {
    const periodEnd = new Date(user.billing_period_end).toLocaleDateString();
    document.getElementById('billing-period').textContent = `Renews ${periodEnd}`;
  } else {
    document.getElementById('billing-period').textContent = user.tier === 'free' ? 'Free plan — no billing' : '—';
  }

  // Upgrade button — hide if already on paid plan
  if (user.tier !== 'free') {
    document.getElementById('upgrade-btn').style.display = 'none';
    document.getElementById('portal-btn').style.display = 'inline-flex';
  }

  // Flash messages from redirect
  const params = new URLSearchParams(window.location.search);
  if (params.get('upgrade') === 'success') showFlash('Subscription activated! Welcome to ' + TIER_LABELS[user.tier] + '.', 'green');
  if (params.get('upgrade') === 'canceled') showFlash('Upgrade canceled — you are still on the Free plan.', 'yellow');
}

// Copy API key
document.getElementById('copy-key-btn').addEventListener('click', () => {
  const key = window._fullApiKey;
  if (!key) return;
  navigator.clipboard.writeText(key).then(() => showFlash('API key copied!', 'green'));
});

// Regenerate API key
document.getElementById('regen-key-btn').addEventListener('click', async () => {
  if (!confirm('Generate a new API key? The current key will stop working immediately.')) return;
  const res = await fetch('/api/auth/regenerate-key', { method: 'POST', headers: getAuthHeaders() });
  if (!res.ok) { showFlash('Failed to regenerate key.', 'red'); return; }
  const data = await res.json();
  window._fullApiKey = data.api_key;
  document.getElementById('api-key-display').textContent = data.api_key.slice(0, 8) + '••••••••••••••••' + data.api_key.slice(-4);
  showFlash('New API key generated.', 'green');
});

// Upgrade button
document.getElementById('upgrade-btn').addEventListener('click', () => {
  document.getElementById('upgrade-modal').style.display = 'flex';
});

document.getElementById('modal-close').addEventListener('click', () => {
  document.getElementById('upgrade-modal').style.display = 'none';
});

document.querySelectorAll('.plan-select-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const plan = btn.dataset.plan;
    btn.textContent = 'Redirecting...';
    btn.disabled = true;
    const res = await fetch('/api/billing/checkout', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ plan }),
    });
    if (!res.ok) {
      showFlash('Checkout failed. Please try again.', 'red');
      btn.textContent = 'Select';
      btn.disabled = false;
      return;
    }
    const data = await res.json();
    window.location.href = data.checkout_url;
  });
});

// Manage billing (portal)
document.getElementById('portal-btn').addEventListener('click', async () => {
  const res = await fetch('/api/billing/portal', { method: 'POST', headers: getAuthHeaders() });
  if (!res.ok) { showFlash('Could not open billing portal.', 'red'); return; }
  const data = await res.json();
  window.location.href = data.portal_url;
});

// Logout
document.getElementById('logout-btn').addEventListener('click', logout);

function showFlash(msg, color) {
  const el = document.getElementById('flash');
  const colors = { green: '#00ff88', yellow: '#facc15', red: '#f85149' };
  el.textContent = msg;
  el.style.color = colors[color] || '#e6edf3';
  el.style.display = 'block';
  setTimeout(() => { el.style.display = 'none'; }, 4000);
}

function showError(msg) {
  document.getElementById('loading').textContent = msg;
}

// Mini analyzer (reuse demo.js logic inline)
document.getElementById('mini-analyze-btn').addEventListener('click', async () => {
  const tb = document.getElementById('mini-tb').value.trim();
  if (!tb) return;
  const resultEl = document.getElementById('mini-result');
  resultEl.textContent = 'Analyzing...';
  try {
    const res = await fetch('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ traceback: tb }),
    });
    const data = await res.json();
    if (!res.ok) { resultEl.textContent = data.detail || 'Error'; return; }
    resultEl.textContent = `[${data.severity?.toUpperCase() || 'INFO'}] ${data.root_cause || ''}\n\nFix: ${data.suggested_fix || ''}`;
  } catch (e) {
    resultEl.textContent = 'Request failed: ' + e.message;
  }
});

// Init
if (!isLoggedIn()) {
  window.location.href = '/?login=1';
} else {
  loadDashboard();
}

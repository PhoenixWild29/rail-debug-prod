// dashboard.js — data fetch + render for dashboard.html

const TIER_LABELS = { free: 'Free', dev: 'Dev — $19/mo', team: 'Team — $99/mo' };
const TIER_COLORS = { free: '#8b949e', dev: '#58a6ff', team: '#00ff88' };
const MONTHLY_LIMITS = { free: 100, dev: 10000, team: null };

async function loadTelemetry() {
  try {
    const res = await fetch('/api/user/telemetry', { headers: getAuthHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    renderTelemetry(data);
  } catch (e) {
    console.error('Telemetry load failed', e);
  }
}

function renderTelemetry(data) {
  const section = document.getElementById('telemetry-section');
  if (!section) return;
  section.style.display = 'block';
  const noData = document.getElementById('no-data');
  if (data.analyses_this_month === 0 || Object.keys(data.analyses_by_language).length === 0) {
    noData.style.display = 'block';
    return;
  }
  noData.style.display = 'none';
  document.getElementById('telemetry-monthly').textContent = data.analyses_this_month;
  document.getElementById('telemetry-avg').textContent = data.avg_severity;
  // Lang badges
  const langContainer = document.getElementById('lang-badges');
  langContainer.innerHTML = Object.entries(data.analyses_by_language).map(([lang, count]) => 
    `<span class="tier-badge">${lang}: ${count}</span>`
  ).join('');
  // Tier badges
  const tierContainer = document.getElementById('tier-badges');
  tierContainer.innerHTML = Object.entries(data.analyses_by_tier).map(([tier, count]) => 
    `<span class="tier-badge">${tier}: ${count}</span>`
  ).join('');
  // Daily chart
  const chart = document.getElementById('daily-chart');
  const maxCount = Math.max(...data.daily_usage.map(d => d.count || 0), 1);
  chart.innerHTML = data.daily_usage.map(day => {
    const barHeight = ((day.count || 0) / maxCount * 100);
    return `
      <div style="flex:1;background:var(--accent-green);border-radius:4px 4px 0 0;height:${barHeight}%;position:relative;min-width:1rem;">
        <div style="position:absolute;bottom:-1.5rem;font-size:0.7rem;color:var(--text-muted);">${day.count || 0}</div>
        <div style="position:absolute;top:-1.25rem;font-size:0.7rem;color:var(--text-muted);white-space:nowrap;left:50%;transform:translateX(-50%);">${day.date.slice(5)}</div>
      </div>
    `;
  }).join('');
}

async function loadDashboard() {
  const res = await fetch('/api/auth/me', { headers: getAuthHeaders() });
  if (res.status === 401) { logout(); return; }
  if (!res.ok) { showError('Failed to load profile.'); return; }
  const user = await res.json();
  renderDashboard(user);
  loadTelemetry();
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

  // Usage — use server-provided limit if available, fall back to JS constant
  const monthly = user.monthly_usage || 0;
  const limit = (user.monthly_limit !== undefined && user.monthly_limit !== null)
    ? user.monthly_limit
    : MONTHLY_LIMITS[user.tier];
  const limitText = limit ? `${monthly} / ${limit}` : `${monthly} / unlimited`;
  document.getElementById('usage-count').textContent = limitText;
  if (limit) {
    const pct = Math.min((monthly / limit) * 100, 100);
    document.getElementById('usage-bar').style.width = `${pct}%`;
    document.getElementById('usage-bar').style.background = pct > 80 ? '#f85149' : '#00ff88';
    if (user.tier === 'free' && pct >= 80) {
      const nudgeEl = document.getElementById('upgrade-nudge');
      if (nudgeEl) {
        document.getElementById('nudge-text').textContent =
          `You've used ${monthly}/${limit} analyses this month — upgrade to Dev for 10,000.`;
        nudgeEl.style.display = 'flex';
        document.getElementById('nudge-upgrade-btn').addEventListener('click', () => {
          document.getElementById('upgrade-modal').style.display = 'flex';
        });
      }
    }
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

  // GitHub section
  if (user.github_username) {
    document.getElementById('github-connected-section').style.display = 'block';
    document.getElementById('github-connect-section').style.display = 'none';
    document.getElementById('github-username-display').textContent = '@' + user.github_username;
    const badge = document.getElementById('github-status-badge');
    badge.textContent = 'Connected';
    badge.style.color = 'var(--accent-green)';
    badge.style.borderColor = 'var(--accent-green)';
    loadGithubAnalyses();
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

  // Plan param auto-open upgrade modal
  const plan = params.get('plan');
  if (user.tier === 'free' && (plan === 'dev' || plan === 'team')) {
    document.getElementById('upgrade-modal').style.display = 'flex';
  }
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
      headers: getAuthHeaders(),
      body: JSON.stringify({ traceback: tb }),
    });
    const data = await res.json();
    if (!res.ok) { resultEl.textContent = data.detail || 'Error'; return; }
    resultEl.textContent = `[${data.severity?.toUpperCase() || 'INFO'}] ${data.root_cause || ''}\n\nFix: ${data.suggested_fix || ''}`;
  } catch (e) {
    resultEl.textContent = 'Request failed: ' + e.message;
  }
});

// GitHub App connection
document.getElementById('connect-github-btn').addEventListener('click', async () => {
  const btn = document.getElementById('connect-github-btn');
  btn.textContent = 'Connecting...';
  btn.disabled = true;
  try {
    const res = await fetch('/api/github/install-url', { headers: getAuthHeaders() });
    if (!res.ok) { showFlash('GitHub App not configured.', 'red'); btn.textContent = 'Connect GitHub'; btn.disabled = false; return; }
    const { install_url } = await res.json();
    window.location.href = install_url;
  } catch (e) {
    showFlash('Could not get install URL.', 'red');
    btn.textContent = 'Connect GitHub';
    btn.disabled = false;
  }
});

async function loadGithubAnalyses() {
  const res = await fetch('/api/github/analyses', { headers: getAuthHeaders() });
  if (!res.ok) return;
  const { analyses } = await res.json();
  if (!analyses || analyses.length === 0) return;
  const container = document.getElementById('github-analyses-items');
  const listEl = document.getElementById('github-analyses-list');
  listEl.style.display = 'block';
  container.innerHTML = analyses.map(a => {
    const result = a.analysis_result || {};
    const severity = result.severity || 'unknown';
    const severityEmoji = { critical: '🔴', high: '🟠', medium: '🟡', low: '🟢' }[severity] || '⚪';
    const date = a.created_at ? new Date(a.created_at).toLocaleDateString() : '';
    const sha = a.head_sha ? a.head_sha.slice(0, 7) : '';
    return `<div style="padding:0.625rem 0.75rem;background:var(--bg-tertiary);border:1px solid var(--border);border-radius:8px;margin-bottom:0.5rem;font-size:0.8rem;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.25rem;">
        <span style="font-family:var(--font-mono);color:var(--text-muted);">${a.repo_full_name}</span>
        <span style="color:var(--text-muted);">${date}</span>
      </div>
      <div>${severityEmoji} <strong>${result.error_type || 'Error'}</strong>${sha ? ` <span style="font-family:var(--font-mono);color:var(--text-muted);">@ ${sha}</span>` : ''}</div>
      <div style="color:var(--text-muted);margin-top:0.25rem;">${result.root_cause || ''}</div>
    </div>`;
  }).join('');
}

// github=connected flash
const _ghParam = new URLSearchParams(window.location.search).get('github');
if (_ghParam === 'connected') showFlash('GitHub connected! CI failures will now be analyzed automatically.', 'green');
if (_ghParam === 'error') showFlash('GitHub connection failed. Please try again.', 'red');

// Init
if (!isLoggedIn()) {
  window.location.href = '/?login=1';
} else {
  loadDashboard();
}

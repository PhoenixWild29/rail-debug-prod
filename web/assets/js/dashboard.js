// dashboard.js — data fetch + render for dashboard.html

const TIER_LABELS = { free: 'Free', dev: 'Dev — $29/mo', team: 'Team — $99/mo' };
const PRICES = {
  dev: { monthly: 29, yearly: 278 },
  team: { monthly: 99, yearly: 950 }
};
let currentPeriod = 'monthly';
const TIER_COLORS = { free: '#8b949e', dev: '#58a6ff', team: '#00ff88' };
const MONTHLY_LIMITS = { free: 100, dev: 10000, team: null };

function updatePrices() {
  document.querySelectorAll('.price').forEach(el => {
    const plan = el.dataset.plan;
    const price = PRICES[plan][currentPeriod];
    const unit = currentPeriod === 'monthly' ? '/mo' : '/yr';
    el.innerHTML = `$${price}<span class="unit" style="font-size:0.875rem;font-weight:400;color:var(--text-muted);">${unit}</span>`;
  });
}

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

async function loadUsage() {
  try {
    const res = await fetch('/api/user/usage', { headers: getAuthHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    const card = document.getElementById('rate-limits-card');
    if (!card) return;
    card.style.display = 'block';

    function renderBar(used, limit, usageId, barId) {
      const el = document.getElementById(usageId);
      const bar = document.getElementById(barId);
      if (!el || !bar) return;
      el.textContent = limit ? `${used} / ${limit}` : `${used} / unlimited`;
      if (limit) {
        const pct = Math.min((used / limit) * 100, 100);
        bar.style.width = pct + '%';
        bar.style.background = pct > 80 ? '#f85149' : '#00ff88';
      } else {
        bar.style.width = '10%';
      }
    }

    renderBar(data.minute.used, data.minute.limit, 'minute-usage', 'minute-bar');
    renderBar(data.daily.used, data.daily.limit, 'daily-usage', 'daily-bar');
    renderBar(data.monthly.used, data.monthly.limit, 'monthly-detail-usage', 'monthly-detail-bar');
  } catch (e) {
    console.error('Usage load failed', e);
  }
}

async function loadWebhooks() {
  try {
    const res = await fetch('/api/webhooks', { headers: getAuthHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('slack-webhook-input').value = data.slack_webhook_url || '';
    document.getElementById('discord-webhook-input').value = data.discord_webhook_url || '';
  } catch (e) {
    console.error('Webhooks load failed', e);
  }
}

async function loadDashboard() {
  const res = await fetch('/api/auth/me', { headers: getAuthHeaders() });
  if (res.status === 401) { logout(); return; }
  if (!res.ok) { showError('Failed to load profile.'); return; }
  const user = await res.json();
  renderDashboard(user);
  loadTelemetry();
  loadUsage();
  loadWebhooks();
  loadTeams();
  loadAnalysisHistory(0);
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

// === TEAM MANAGEMENT ===

let currentTeam = null;
let currentTeamRole = null;

async function loadTeams() {
  try {
    const res = await fetch('/api/teams', { headers: getAuthHeaders() });
    if (!res.ok) return;
    const teams = await res.json();
    if (teams.length > 0) {
      currentTeam = teams[0];
      currentTeamRole = teams[0].role;
      renderActiveTeam(teams[0]);
    }
  } catch (e) {
    console.error('Teams load failed', e);
  }
}

function renderActiveTeam(team) {
  document.getElementById('team-none-section').style.display = 'none';
  document.getElementById('team-active-section').style.display = 'block';
  document.getElementById('team-name-display').textContent = team.name;
  const badge = document.getElementById('team-status-badge');
  badge.textContent = team.role.charAt(0).toUpperCase() + team.role.slice(1);
  badge.style.color = 'var(--accent-green)';
  badge.style.borderColor = 'var(--accent-green)';

  // Show invite + delete for owner/admin
  if (team.role === 'owner' || team.role === 'admin') {
    document.getElementById('team-invite-section').style.display = 'block';
  }
  if (team.role === 'owner') {
    document.getElementById('team-owner-actions').style.display = 'block';
  }

  loadTeamMembers(team.id);
  loadTeamAnalyses(team.id);
}

async function loadTeamMembers(teamId) {
  try {
    const res = await fetch(`/api/teams/${teamId}/members`, { headers: getAuthHeaders() });
    if (!res.ok) return;
    const members = await res.json();
    const container = document.getElementById('team-members-list');
    container.innerHTML = members.map(m => {
      const roleColor = m.role === 'owner' ? 'var(--accent-green)' : m.role === 'admin' ? 'var(--accent-blue)' : 'var(--text-muted)';
      const removeBtn = (currentTeamRole === 'owner' || currentTeamRole === 'admin') && m.role !== 'owner'
        ? `<button class="btn btn-danger remove-member-btn" data-user-id="${m.user_id}" style="padding:0.25rem 0.5rem;font-size:0.75rem;">Remove</button>`
        : '';
      return `<div style="display:flex;justify-content:space-between;align-items:center;padding:0.5rem 0.75rem;background:var(--bg-tertiary);border:1px solid var(--border);border-radius:8px;margin-bottom:0.375rem;font-size:0.875rem;">
        <span>${m.email}</span>
        <div style="display:flex;align-items:center;gap:0.5rem;">
          <span style="font-size:0.75rem;color:${roleColor};font-weight:500;">${m.role}</span>
          ${removeBtn}
        </div>
      </div>`;
    }).join('');

    // Bind remove buttons
    container.querySelectorAll('.remove-member-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const userId = btn.dataset.userId;
        if (!confirm('Remove this member from the team?')) return;
        const res = await fetch(`/api/teams/${teamId}/members/${userId}`, { method: 'DELETE', headers: getAuthHeaders() });
        if (!res.ok) { showFlash('Failed to remove member.', 'red'); return; }
        showFlash('Member removed.', 'green');
        loadTeamMembers(teamId);
      });
    });
  } catch (e) {
    console.error('Members load failed', e);
  }
}

async function loadTeamAnalyses(teamId) {
  try {
    const res = await fetch(`/api/teams/${teamId}/analyses`, { headers: getAuthHeaders() });
    if (!res.ok) return;
    const analyses = await res.json();
    const container = document.getElementById('team-analyses-list');
    if (analyses.length === 0) {
      container.innerHTML = '<div style="color:var(--text-muted);font-size:0.875rem;">No shared analyses yet.</div>';
      return;
    }
    const severityEmoji = { critical: '🔴', high: '🟠', medium: '🟡', low: '🟢' };
    container.innerHTML = analyses.slice(0, 10).map(a => {
      const emoji = severityEmoji[a.severity] || '⚪';
      const date = a.created_at ? new Date(a.created_at).toLocaleDateString() : '';
      return `<div style="padding:0.5rem 0.75rem;background:var(--bg-tertiary);border:1px solid var(--border);border-radius:8px;margin-bottom:0.375rem;font-size:0.8rem;display:flex;justify-content:space-between;">
        <span>${emoji} ${a.language || 'unknown'} — ${a.tier_used || '?'}</span>
        <span style="color:var(--text-muted);">${date}</span>
      </div>`;
    }).join('');
  } catch (e) {
    console.error('Team analyses load failed', e);
  }
}

// Create team
document.getElementById('create-team-btn').addEventListener('click', async () => {
  const name = document.getElementById('team-name-input').value.trim();
  if (!name) { showFlash('Enter a team name.', 'yellow'); return; }
  const res = await fetch('/api/teams', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ name }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    showFlash(err.detail || 'Failed to create team.', 'red');
    return;
  }
  showFlash('Team created!', 'green');
  loadTeams();
});

// Invite member
document.getElementById('invite-member-btn').addEventListener('click', async () => {
  if (!currentTeam) return;
  const email = document.getElementById('invite-email-input').value.trim();
  if (!email) { showFlash('Enter an email address.', 'yellow'); return; }
  const res = await fetch(`/api/teams/${currentTeam.id}/invite`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ email }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    showFlash(err.detail || 'Failed to invite member.', 'red');
    return;
  }
  document.getElementById('invite-email-input').value = '';
  showFlash('Member invited!', 'green');
  loadTeamMembers(currentTeam.id);
});

// Delete team
document.getElementById('delete-team-btn').addEventListener('click', async () => {
  if (!currentTeam) return;
  if (!confirm('Delete this team? All shared analyses will be unshared.')) return;
  const res = await fetch(`/api/teams/${currentTeam.id}`, { method: 'DELETE', headers: getAuthHeaders() });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    showFlash(err.detail || 'Failed to delete team.', 'red');
    return;
  }
  currentTeam = null;
  currentTeamRole = null;
  document.getElementById('team-active-section').style.display = 'none';
  document.getElementById('team-none-section').style.display = 'block';
  document.getElementById('team-status-badge').textContent = 'No team';
  document.getElementById('team-status-badge').style.color = 'var(--text-muted)';
  document.getElementById('team-status-badge').style.borderColor = 'var(--border)';
  showFlash('Team deleted.', 'green');
});

// Webhook save
document.getElementById('save-webhooks-btn').addEventListener('click', async () => {
  const slack = document.getElementById('slack-webhook-input').value.trim();
  const discord = document.getElementById('discord-webhook-input').value.trim();
  const res = await fetch('/api/webhooks', {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: new URLSearchParams({ slack_webhook_url: slack, discord_webhook_url: discord }),
  });
  if (!res.ok) {
    showFlash('Failed to save webhook settings.', 'red');
    return;
  }
  showFlash('Webhook settings saved!', 'green');
});

// Webhook test
document.getElementById('test-webhooks-btn').addEventListener('click', async () => {
  const res = await fetch('/api/webhooks/test', {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  if (!res.ok) {
    showFlash('Failed to send test notifications.', 'red');
    return;
  }
  showFlash('Test notifications sent!', 'green');
});

// Analysis History — RAIL-039
let analysisOffset = 0;
let analysisTotal = 0;
let analysisList = [];

async function loadAnalysisHistory(offset = 0, append = false) {
  try {
    const res = await fetch(`/api/analyses?offset=${offset}`, { headers: getAuthHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    if (!append) {
      analysisList = data.analyses;
      analysisOffset = data.analyses.length;
    } else {
      analysisList = analysisList.concat(data.analyses);
      analysisOffset += data.analyses.length;
    }
    analysisTotal = data.total;
    renderAnalysisHistory();
  } catch (e) {
    console.error('History load failed', e);
    document.getElementById('analysis-history-list').innerHTML = '<div style="color:var(--text-muted);">Failed to load history.</div>';
  }
}

function renderAnalysisHistory() {
  const listEl = document.getElementById('analysis-history-list');
  const loadMoreBtn = document.getElementById('load-more-analyses');
  if (analysisList.length === 0) {
    listEl.innerHTML = '<div style="color:var(--text-muted);padding:2rem;text-align:center;">No analyses yet — try analyzing an error above</div>';
    loadMoreBtn.style.display = 'none';
    return;
  }
  listEl.innerHTML = analysisList.map(a => {
    const severityColor = {critical: '#f85149', high: '#f59e0b', medium: '#eab308', low: '#22c55e'}[a.severity] || '#6b7280';
    const tierLabel = a.tier_used === 'regex' ? 'Regex' : a.tier_used ? a.tier_used.charAt(0).toUpperCase() + a.tier_used.slice(1) : '?';
    const date = new Date(a.created_at).toLocaleDateString();
    return `
      <div style="display:flex;align-items:center;gap:1rem;padding:1rem;border:1px solid var(--border);border-radius:12px;margin-bottom:0.75rem;background:var(--bg-tertiary);">
        <div style="flex:1;">
          <div style="font-weight:600;margin-bottom:0.25rem;" title="${a.title}">${a.title.length > 60 ? a.title.slice(0,60) + '...' : a.title}</div>
          <div style="display:flex;gap:0.5rem;align-items:center;font-size:0.875rem;color:var(--text-muted);">
            <span class="tier-badge" style="background:${severityColor}20;color:${severityColor};">${a.severity.toUpperCase()}</span>
            <span class="tier-badge">${a.language}</span>
            <span class="tier-badge">${tierLabel}</span>
            <span>${date}</span>
          </div>
        </div>
        <button class="btn btn-primary view-analysis-btn" data-id="${a.id}">View</button>
      </div>
    `;
  }).join('');
  loadMoreBtn.style.display = analysisOffset < analysisTotal ? 'inline-flex' : 'none';
  document.querySelectorAll('.view-analysis-btn').forEach(btn => {
    btn.addEventListener('click', (e) => showAnalysisDetail(e.target.dataset.id));
  });
}

async function showAnalysisDetail(id) {
  try {
    const res = await fetch(`/api/analyses/${id}`, { headers: getAuthHeaders() });
    if (!res.ok) {
      showFlash('Analysis not found.', 'red');
      return;
    }
    const data = await res.json();
    const modalBody = document.getElementById('analysis-detail-body');
    const severityColor = {critical: '#f85149', high: '#f59e0b', medium: '#eab308', low: '#22c55e'}[data.severity] || '#6b7280';
    const tierLabel = data.tier_used || data.model_used || '?';
    const date = new Date(data.created_at).toLocaleString();
    modalBody.innerHTML = `
      <h3 style="font-size:1.25rem;font-weight:700;margin-bottom:1rem;">${data.title || 'Analysis'}</h3>
      <div style="display:flex;gap:1rem;font-size:0.875rem;margin-bottom:1.5rem;">
        <span class="tier-badge" style="background:${severityColor}20;color:${severityColor};">${data.severity ? data.severity.toUpperCase() : ''}</span>
        <span class="tier-badge">${data.language || ''}</span>
        <span class="tier-badge">${tierLabel}</span>
        <span style="color:var(--text-muted);">${date}</span>
      </div>
      <div style="margin-bottom:1.5rem;">
        <div class="label" style="margin-bottom:0.5rem;">Traceback</div>
        <pre style="background:var(--bg-tertiary);border:1px solid var(--border);border-radius:8px;padding:1rem;font-size:0.875rem;max-height:300px;overflow:auto;white-space:pre-wrap;">${(data.traceback_text || '').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
      </div>
      <div style="margin-bottom:1.5rem;">
        <div class="label" style="margin-bottom:0.5rem;">Root Cause</div>
        <div style="background:var(--bg-tertiary);border:1px solid var(--border);border-radius:8px;padding:1rem;">${data.root_cause || ''}</div>
      </div>
      <div style="margin-bottom:1.5rem;">
        <div class="label" style="margin-bottom:0.5rem;">Suggested Fix</div>
        <div style="position:relative;">
          <div style="background:var(--bg-tertiary);border:1px solid var(--border);border-radius:8px;padding:1rem;">${data.suggested_fix || ''}</div>
          <button class="copy-fix-btn btn btn-secondary" data-fix="${data.suggested_fix || ''}" style="position:absolute;top:0.5rem;right:0.5rem;padding:0.25rem 0.75rem;font-size:0.75rem;">Copy fix</button>
        </div>
      </div>
      ${typeof currentTeam !== 'undefined' && currentTeam ? `
        <div>
          <button class="btn btn-secondary share-team-btn" data-id="${id}">Share with team</button>
        </div>
      ` : ''}
    `;
    // Copy buttons
    modalBody.querySelectorAll('.copy-fix-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        navigator.clipboard.writeText(btn.dataset.fix).then(() => showFlash('Fix copied!', 'green'));
      });
    });
    // Share stub
    modalBody.querySelector('.share-team-btn')?.addEventListener('click', () => {
      showFlash('Share with team coming in RAIL-041.', 'yellow');
    });
    document.getElementById('analysis-detail-modal').style.display = 'flex';
  } catch (e) {
    showFlash('Failed to load details.', 'red');
  }
}

document.getElementById('load-more-analyses').addEventListener('click', () => loadAnalysisHistory(analysisOffset, true));
document.getElementById('close-detail-modal').addEventListener('click', () => document.getElementById('analysis-detail-modal').style.display = 'none');
document.getElementById('analysis-detail-modal').addEventListener('click', (e) => {
  if (e.target.id === 'analysis-detail-modal') e.target.style.display = 'none';
});

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

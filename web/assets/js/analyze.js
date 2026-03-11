// analyze.js — Full analysis page logic
// Includes auth check + analyze handler

// Reuse auth helpers
function getAuthHeaders() {
  const token = localStorage.getItem('rd_token');
  return token ? { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' } : { 'Content-Type': 'application/json' };
}

function isLoggedIn() {
  const token = localStorage.getItem('rd_token');
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

// Detect language from traceback (client-side preview)
function detectLanguage(traceback) {
  if (!traceback) return 'Unknown';
  const lower = traceback.toLowerCase();
  if (lower.includes('file &quot;') || lower.includes('traceback (most recent call last)')) return 'Python';
  if (lower.includes('at ')) return 'Java';
  if (lower.includes('node.js') || lower.includes('npm err!')) return 'Node.js';
  if (lower.includes('thread') && lower.includes('rust')) return 'Rust';
  if (lower.includes('go') && (lower.includes('runtime') || lower.includes('panic'))) return 'Go';
  if (lower.includes('solidity') || lower.includes('contract')) return 'Solidity';
  return 'Unknown';
}

// Main analyze function
async function analyzeTraceback() {
  const traceback = document.getElementById('traceback-input').value.trim();
  if (!traceback) {
    showError('Paste a traceback first.');
    return;
  }

  const deep = document.getElementById('deep-toggle').checked;
  const analyzeBtn = document.getElementById('analyze-btn');
  const results = document.getElementById('results');
  const loadingEl = document.getElementById('loading-state');

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = 'Analyzing';
  analyzeBtn.classList.add('analyzing');
  loadingEl.style.display = 'block';
  results.style.display = 'none';

  try {
    const response = await fetch('/api/analyze', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ traceback, deep }),
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || 'Analysis failed');
    }

    // Update language badge (backend or fallback)
    const langBadge = document.getElementById('lang-badge');
    langBadge.textContent = data.language || detectLanguage(traceback);
    langBadge.dataset.lang = langBadge.textContent.toLowerCase();

    // Tier badge
    document.getElementById('tier-badge').textContent = data.tier || 'Regex';

    // Severity badge
    const sevBadge = document.getElementById('severity-badge');
    const severity = data.severity || 'low';
    sevBadge.textContent = severity.toUpperCase();
    sevBadge.className = `severity-badge severity-${severity}`;
    sevBadge.style.display = 'inline-flex';

    // Error type + message
    document.getElementById('error-type').innerHTML = `<strong>${data.error_type || 'Error'}</strong>${data.error_message ? `: ${data.error_message}` : ''}`;

    // Root cause
    document.getElementById('root-cause').textContent = data.root_cause || 'No root cause identified.';

    // File + line
    const fileLine = document.getElementById('file-line');
    if (data.file_path) {
      fileLine.textContent = `${data.file_path}${data.line_number ? `:${data.line_number}` : ''}`;
      fileLine.style.display = 'block';
    } else {
      fileLine.style.display = 'none';
    }

    // Suggested fix
    const fixEl = document.getElementById('suggested-fix');
    fixEl.textContent = data.suggested_fix || 'No fix suggested.';
    fixEl.parentElement.style.display = 'block';

    results.scrollIntoView({ behavior: 'smooth' });
    results.style.display = 'block';
  } catch (error) {
    showError(`Error: ${error.message}`);
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = 'Analyze';
    analyzeBtn.classList.remove('analyzing');
    loadingEl.style.display = 'none';
  }
}

function showError(msg) {
  const errorEl = document.getElementById('error-msg');
  errorEl.textContent = msg;
  errorEl.style.display = 'block';
  setTimeout(() => {
    errorEl.style.display = 'none';
  }, 5000);
}

// Event listeners
document.addEventListener('DOMContentLoaded', () => {
  if (!isLoggedIn()) {
    window.location.href = '/?login=1';
    return;
  }

  const analyzeBtn = document.getElementById('analyze-btn');
  const input = document.getElementById('traceback-input');
  const deepToggle = document.getElementById('deep-toggle');

  if (analyzeBtn) analyzeBtn.addEventListener('click', analyzeTraceback);

  // Live language detection
  input.addEventListener('input', () => {
    const lang = detectLanguage(input.value);
    document.getElementById('lang-badge').textContent = lang;
  });

  // Example load button
  const exampleBtn = document.getElementById('load-example');
  if (exampleBtn) {
    exampleBtn.addEventListener('click', () => {
      input.value = `Traceback (most recent call last):
  File &quot;app.py&quot;, line 42, in &lt;module&gt;
    result = db.query(&quot;SELECT * FROM users WHERE id = %s&quot;, user_id)
psycopg2.ProgrammingError: syntax error at or near \&quot;%\&quot;
LINE 1: SELECT * FROM users WHERE id = %s
`;
      input.dispatchEvent(new Event('input'));
      input.focus();
    });
  }

  // Auto-resize textarea
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = input.scrollHeight + 'px';
  });
});

// Live demo widget for Rail Debug
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('traceback-input');
  const btn = document.getElementById('analyze-btn');
  const output = document.getElementById('demo-output');
  const exampleBtn = document.getElementById('load-example');

  if (!input || !btn || !output) return;

  // Sample Python KeyError traceback
  const exampleTraceback = `Traceback (most recent call last):
  File "app.py", line 42, in <module>
    print(users[user_id])
KeyError: 'phoenixwild'`;

  if (exampleBtn) {
    exampleBtn.addEventListener('click', () => {
      input.value = exampleTraceback;
      input.focus();
    });
  }

  btn.addEventListener('click', async () => {
    const traceback = input.value.trim();
    if (!traceback) {
      output.innerHTML = '<p class="text-red-400">Please paste a traceback.</p>';
      return;
    }

    btn.disabled = true;
    btn.textContent = 'Analyzing';
    btn.classList.add('analyzing');
    output.innerHTML = '<div class="text-accent-green analyzing">Analyzing with 4-tier AI cascade...</div>';

    try {
      const res = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ traceback, mode: 'auto' })
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      renderOutput(data);
    } catch (err) {
      output.innerHTML = `<p class="text-red-400">Analysis unavailable — server may be starting up. Try again in a moment. (${err.message})</p>`;
    } finally {
      btn.disabled = false;
      btn.textContent = 'Analyze →';
      btn.classList.remove('analyzing');
    }
  });

  function renderOutput(data) {
    const severityClass = `severity-${data.severity?.toLowerCase() || 'low'}`;
    output.innerHTML = `
      <div class="bg-bg-secondary p-6 rounded-lg border border-border">
        <div class="flex items-center mb-4">
          <span class="px-3 py-1 rounded-full text-sm font-mono ${severityClass} text-black">${data.severity || 'LOW'}</span>
          <span class="ml-2 text-muted font-mono">Tier ${data.tier}</span>
        </div>
        <h3 class="text-xl font-bold mb-2">Root Cause</h3>
        <p class="mb-4 text-text-primary">${data.root_cause || 'N/A'}</p>
        <h3 class="text-xl font-bold mb-2">Suggested Fix</h3>
        <pre class="bg-bg-tertiary p-4 rounded border border-border font-mono text-sm overflow-auto">${data.suggested_fix || 'N/A'}</pre>
      </div>
    `;
  }
});

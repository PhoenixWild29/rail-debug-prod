// login.js — Auth modal for index.html landing page
// Uses auth.js helpers: getToken, setToken, isLoggedIn, getAuthHeaders

document.addEventListener('DOMContentLoaded', () =&gt; {
  const urlParams = new URLSearchParams(window.location.search);
  if (urlParams.get('login') === '1') {
    if (typeof isLoggedIn === 'function' &amp;&amp; isLoggedIn()) {
      window.location.href = '/dashboard.html';
      return;
    }
    showAuthModal();
  }

  // Tab switching
  document.querySelectorAll('[data-tab]').forEach(button =&gt; {
    button.addEventListener('click', () =&gt; {
      const targetId = button.dataset.tab;
      document.querySelectorAll('.tab-pane').forEach(pane =&gt; pane.classList.add('hidden'));
      document.getElementById(targetId).classList.remove('hidden');
      document.querySelectorAll('[data-tab]').forEach(btn =&gt; btn.classList.remove('tab-active'));
      button.classList.add('tab-active');
    });
  });

  // Backdrop close
  const modal = document.getElementById('auth-modal');
  modal.addEventListener('click', (e) =&gt; {
    if (e.target === modal) {
      hideAuthModal();
    }
  });
});

function showAuthModal() {
  document.getElementById('auth-modal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function hideAuthModal() {
  document.getElementById('auth-modal').style.display = 'none';
  document.body.style.overflow = '';
}

function showError(errorId, message) {
  const errorEl = document.getElementById(errorId);
  errorEl.textContent = message;
  errorEl.classList.remove('hidden');
  setTimeout(() =&gt; errorEl.classList.add('hidden'), 10000);
}

// Login form
document.addEventListener('DOMContentLoaded', () =&gt; {
  const loginForm = document.getElementById('login-form');
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) =&gt; {
      e.preventDefault();
      const email = document.getElementById('login-email').value;
      const password = document.getElementById('login-password').value;
      if (!email || !password) return;
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });
        if (!res.ok) {
          const err = await res.json().catch(() =&gt; ({}));
          showError('login-error', err.detail || err.message || 'Invalid credentials');
          return;
        }
        const data = await res.json();
        if (typeof setToken === 'function') setToken(data.token);
        window.location.href = '/dashboard.html';
      } catch (err) {
        showError('login-error', 'Network error. Try again.');
      }
    });
  }
});

// Register form
document.addEventListener('DOMContentLoaded', () =&gt; {
  const registerForm = document.getElementById('register-form');
  if (registerForm) {
    registerForm.addEventListener('submit', async (e) =&gt; {
      e.preventDefault();
      const email = document.getElementById('register-email').value;
      const password = document.getElementById('register-password').value;
      if (!email || !password) return;
      try {
        const res = await fetch('/api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password })
        });
        if (!res.ok) {
          const err = await res.json().catch(() =&gt; ({}));
          showError('register-error', err.detail || err.message || 'Registration failed');
          return;
        }
        const data = await res.json();
        if (typeof setToken === 'function') setToken(data.token);
        window.location.href = '/dashboard.html';
      } catch (err) {
        showError('register-error', 'Network error. Try again.');
      }
    });
  }
});

// Waitlist form handler
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('waitlist-form');
  const status = document.getElementById('waitlist-status');

  if (!form) return;

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(form);
    const data = {
      email: formData.get('email'),
      first_name: formData.get('first_name') || null,
      tier_interest: formData.get('tier_interest') || 'free'
    };

    // Basic email validation
    const emailRegex = /^[^\\s@]+@[^\\s@]+\\.[^\\s@]+$/;
    if (!emailRegex.test(data.email)) {
      showStatus('Please enter a valid email.', 'error');
      return;
    }

    const submitBtn = form.querySelector('button[type="submit"]');
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Joining...';

    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });

      const result = await res.json();

      if (res.ok) {
        showStatus(result.message || "You're on the list. We'll be in touch. 🚀", 'success');
        form.reset();
      } else {
        showStatus(result.detail || 'Something went wrong — try again.', 'error');
      }
    } catch (err) {
      showStatus('Network error — try again.', 'error');
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = originalText;
    }
  });

  function showStatus(message, type) {
    if (status) {
      status.textContent = message;
      status.className = `mt-4 p-4 rounded-lg w-full text-center font-mono ${type === 'success' ? 'bg-accent-green/20 text-accent-green border-accent-green/50 border' : 'bg-red-500/20 text-red-400 border-red-500/50 border'}`;
      status.style.display = 'block';
    }
  }
});

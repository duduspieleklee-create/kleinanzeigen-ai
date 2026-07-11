// Auth forms — service worker registration + password show/hide toggle.
// Shared by login.html and register.html.

export function initAuthForms() {
  // Register service worker so the app is installable as a PWA from first page.
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  }

  // Password show/hide toggle
  document.querySelectorAll('.password-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const input = document.getElementById(btn.dataset.target)
      if (!input) return
      const showing = input.type === 'text'
      input.type = showing ? 'password' : 'text'
      btn.textContent = showing ? 'Anzeigen' : 'Verbergen'
      btn.setAttribute('aria-label', showing ? 'Passwort anzeigen' : 'Passwort verbergen')
    })
  })
}

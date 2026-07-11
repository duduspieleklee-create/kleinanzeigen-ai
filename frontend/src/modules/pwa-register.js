// PWA register — lightweight SW registration (used on verify_email.html, etc.)
export function initPwaRegister() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  }
}

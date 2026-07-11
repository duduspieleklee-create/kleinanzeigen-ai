// PWA install prompt — capture beforeinstallprompt, show button, handle iOS.
export function initPwaInstall() {
  const btn = document.getElementById('pwa-install-btn')
  const iosHint = document.getElementById('pwa-ios-hint')
  if (!btn) return

  let deferredPrompt = null
  window.addEventListener('beforeinstallprompt', (e) => {
    deferredPrompt = e
    btn.hidden = false
  })

  window.addEventListener('appinstalled', () => {
    btn.hidden = true
    if (iosHint) iosHint.hidden = true
    deferredPrompt = null
  })

  btn.addEventListener('click', () => {
    if (!deferredPrompt) return
    deferredPrompt.prompt()
    deferredPrompt.userChoice.finally(() => {
      deferredPrompt = null
      btn.hidden = true
    })
  })

  // iOS detection: no beforeinstallprompt, so offer the manual path.
  const isIOS = /iP(hone|od|ad)/.test(navigator.userAgent) ||
    (navigator.userAgent.includes('Macintosh') && 'ontouchend' in document)
  const standalone = window.matchMedia('(display-mode: standalone)').matches ||
    window.navigator.standalone === true
  if (isIOS && !standalone && iosHint) {
    iosHint.hidden = false
  }
}

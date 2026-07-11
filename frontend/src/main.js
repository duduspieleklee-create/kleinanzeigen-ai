// Entry point — Vite bundles feature modules into a single main.js
// Loaded by Jinja2 templates via <script type="module" src="/static/main.js"></script>
//
// Modules imported here replace inline <script> blocks in templates.
// Page-specific complex scripts (dashboard.html, settings.html) remain inline
// for now — they are extracted progressively in later passes.

import { initSmartSearch } from './modules/smart-search.js'
import { initResultsSearch } from './modules/results-search.js'
import { initAuthForms } from './modules/auth-forms.js'
import { initPwaRegister } from './modules/pwa-register.js'
import { initPwaInstall } from './modules/pwa-install.js'

function boot() {
  initSmartSearch()
  initResultsSearch()
  initAuthForms()
  initPwaRegister()
  initPwaInstall()
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot)
} else {
  boot()
}

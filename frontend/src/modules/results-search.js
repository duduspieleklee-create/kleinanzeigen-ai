// Results page — submit search on Enter.
export function initResultsSearch() {
  const input = document.getElementById('smart-search-input')
  if (!input) return
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      const q = input.value.trim()
      if (q) window.location.href = '/dashboard?keywords=' + encodeURIComponent(q)
    }
  })
}

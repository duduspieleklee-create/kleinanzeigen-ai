// Results page — start a new search from the smart-search box.
// Both the "Suchen" button and the Enter key navigate to the dashboard with
// the typed keywords, so the two entry points share one code path.
export function initResultsSearch() {
  const input = document.getElementById('smart-search-input')
  if (!input) return

  function startSearch() {
    const q = input.value.trim()
    if (q) window.location.href = '/dashboard?keywords=' + encodeURIComponent(q)
  }

  // Exposed for the inline onclick on the results-page "Suchen" button.
  window.resultsStartSearch = startSearch

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      startSearch()
    }
  })
}

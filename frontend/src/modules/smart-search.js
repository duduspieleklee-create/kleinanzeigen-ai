// Smart Search Suggestions — autocomplete dropdown for the search input.
// Wires the #smart-search-input field to /api/search-suggestions.

export function initSmartSearch() {
  const input = document.getElementById('smart-search-input')
  const list = document.getElementById('smart-search-suggestions')
  if (!input || !list) return

  let activeIndex = -1
  let lastQuery = ''

  function trackClick(term) {
    fetch('/api/search-suggestions/click', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword: lastQuery, suggestion: term, suggestion_type: 'generic' }),
    }).catch(() => {})
  }

  function render(items) {
    list.innerHTML = ''
    activeIndex = -1
    if (!items.length) { list.style.display = 'none'; return }
    items.forEach((term) => {
      const li = document.createElement('li')
      li.textContent = term
      li.addEventListener('mousedown', (e) => {
        e.preventDefault()
        trackClick(term)
        input.value = term
        list.style.display = 'none'
        input.dispatchEvent(new Event('input'))
      })
      list.appendChild(li)
    })
    list.style.display = 'block'
  }

  function flatten(data) {
    const out = []
    if (!data || !data.suggestions) return out
    Object.keys(data.suggestions).forEach((group) => {
      data.suggestions[group].forEach((term) => {
        if (out.indexOf(term) === -1) out.push(term)
      })
    })
    return out.slice(0, 12)
  }

  function fetchSuggestions() {
    const q = input.value.trim()
    lastQuery = q
    if (q.length < 2) { list.style.display = 'none'; return }
    fetch('/api/search-suggestions?query=' + encodeURIComponent(q), {
      headers: { 'Accept': 'application/json' },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => render(flatten(data)))
      .catch(() => { list.style.display = 'none' })
  }

  input.addEventListener('input', () => {
    clearTimeout(input._debounceTimer)
    input._debounceTimer = setTimeout(fetchSuggestions, 200)
  })
  input.addEventListener('focus', () => {
    if (input.value.trim().length >= 2) fetchSuggestions()
  })
  input.addEventListener('keydown', (e) => {
    const items = list.querySelectorAll('li')
    if (!items.length) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      activeIndex = (activeIndex + 1) % items.length
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      activeIndex = (activeIndex - 1 + items.length) % items.length
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      e.preventDefault()
      trackClick(items[activeIndex].textContent)
      items[activeIndex].dispatchEvent(new Event('mousedown'))
      return
    } else if (e.key === 'Escape') {
      list.style.display = 'none'
      return
    }
    items.forEach((li, i) => li.classList.toggle('active', i === activeIndex))
  })
  input.addEventListener('blur', () => {
    setTimeout(() => { list.style.display = 'none' }, 150)
  })
  window.addEventListener('scroll', () => { list.style.display = 'none' })
}

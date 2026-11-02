import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// jsdom does not implement scrolling; the app calls it after navigation.
window.scrollTo = () => {}

// Node 26 exposes its own (file-backed, here undefined) global localStorage that shadows
// jsdom's. Provide an in-memory Storage so persistence can be tested.
if (!window.localStorage) {
  const data = new Map()
  const storage = {
    getItem: (k) => (data.has(String(k)) ? data.get(String(k)) : null),
    setItem: (k, v) => data.set(String(k), String(v)),
    removeItem: (k) => data.delete(String(k)),
    clear: () => data.clear(),
    key: (i) => [...data.keys()][i] ?? null,
    get length() {
      return data.size
    },
  }
  Object.defineProperty(window, 'localStorage', { value: storage, configurable: true })
  Object.defineProperty(globalThis, 'localStorage', { value: storage, configurable: true })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  try {
    window.localStorage.clear()
  } catch {
    /* ignore */
  }
  document.documentElement.lang = 'en'
  document.documentElement.dir = 'ltr'
  document.documentElement.classList.remove('dark')
  document.documentElement.style.colorScheme = ''
  window.history.replaceState(null, '', '/') // views live in the hash; samples in the query
})

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

export const THEME_KEY = 'fair.theme'
export const THEMES = ['light', 'dark', 'system']
const QUERY = '(prefers-color-scheme: dark)'

const ThemeContext = createContext(null)

export function readStoredTheme() {
  try {
    const v = window.localStorage.getItem(THEME_KEY)
    return THEMES.includes(v) ? v : 'system'
  } catch {
    return 'system'
  }
}

function systemPrefersDark() {
  try {
    return !!window.matchMedia?.(QUERY).matches
  } catch {
    return false
  }
}

export function resolveTheme(preference) {
  return preference === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : preference
}

/** Same logic as the inline script in index.html (which runs before first paint). */
export function applyTheme(resolved) {
  const root = document.documentElement
  root.classList.toggle('dark', resolved === 'dark')
  root.style.colorScheme = resolved
}

export function ThemeProvider({ children }) {
  const [preference, setPreferenceState] = useState(readStoredTheme)
  const [resolved, setResolved] = useState(() => resolveTheme(readStoredTheme()))

  useEffect(() => {
    const update = () => {
      const r = resolveTheme(preference)
      setResolved(r)
      applyTheme(r)
    }
    update()
    if (preference !== 'system') return undefined
    const mql = window.matchMedia?.(QUERY)
    mql?.addEventListener?.('change', update)
    return () => mql?.removeEventListener?.('change', update)
  }, [preference])

  const setPreference = useCallback((next) => {
    if (!THEMES.includes(next)) return
    setPreferenceState(next)
    try {
      window.localStorage.setItem(THEME_KEY, next)
    } catch {
      /* storage unavailable: theme still applies for this session */
    }
  }, [])

  const value = useMemo(() => ({ preference, resolved, setPreference }), [preference, resolved, setPreference])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>')
  return ctx
}

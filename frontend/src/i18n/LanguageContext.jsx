import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { STRINGS } from './strings.js'

const STORAGE_KEY = 'fair.lang'
const LanguageContext = createContext(null)

function readStoredLang() {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('lang')
    if (fromUrl === 'ar' || fromUrl === 'en') return fromUrl
  } catch {
    /* ignore malformed URL */
  }
  try {
    const v = window.localStorage.getItem(STORAGE_KEY)
    return v === 'ar' || v === 'en' ? v : null
  } catch {
    return null
  }
}

export function lookup(lang, key) {
  return key.split('.').reduce((node, part) => (node == null ? undefined : node[part]), STRINGS[lang])
}

export function interpolate(template, vars = {}) {
  return String(template).replace(/\{(\w+)\}/g, (m, name) => (name in vars ? String(vars[name]) : m))
}

export function translate(lang, key, vars) {
  const value = lookup(lang, key)
  if (value === undefined) return key
  return typeof value === 'string' ? interpolate(value, vars) : value
}

export function LanguageProvider({ children, initialLang }) {
  const [lang, setLang] = useState(() => initialLang || readStoredLang() || 'en')
  const dir = lang === 'ar' ? 'rtl' : 'ltr'

  useEffect(() => {
    document.documentElement.lang = lang
    document.documentElement.dir = dir
    try {
      window.localStorage.setItem(STORAGE_KEY, lang)
    } catch {
      /* storage unavailable: language still works for this session */
    }
  }, [lang, dir])

  const t = useCallback((key, vars) => translate(lang, key, vars), [lang])
  const value = useMemo(() => ({ lang, dir, setLang, t }), [lang, dir, t])
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useLang() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLang must be used inside <LanguageProvider>')
  return ctx
}

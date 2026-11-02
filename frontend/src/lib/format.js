import { STRINGS } from '../i18n/strings.js'
import { interpolate } from '../i18n/LanguageContext.jsx'

// Latin digits in both languages so amounts match the quoted source text.
const NUMBER_LOCALE = { en: 'en-US', ar: 'ar-u-nu-latn' }
const DATE_LOCALE = { en: 'en-US', ar: 'ar-SA-u-nu-latn-ca-gregory' }

/** Pick the plural form for n from a {one, other, few, ...} map. */
export function pluralFrom(lang, forms, n) {
  const category = new Intl.PluralRules(lang === 'ar' ? 'ar' : 'en-US').select(n)
  return interpolate(forms[category] ?? forms.other, { n })
}

/** Count with correct plural form, e.g. plural('ar', 'day', 3) -> "3 أيام". */
export function plural(lang, unit, n) {
  return pluralFrom(lang, STRINGS[lang].units[unit], n)
}

/**
 * Format a backend Decimal string ("14.49", "15", "154.00") without changing its value.
 * Returns null for null/undefined/invalid input so callers can show "not stated".
 */
export function formatAmount(value, lang) {
  if (value === null || value === undefined || value === '') return null
  const s = String(value).trim()
  if (!/^-?\d+(\.\d+)?$/.test(s)) return null
  const decimals = Math.max(2, (s.split('.')[1] || '').length)
  return new Intl.NumberFormat(NUMBER_LOCALE[lang], {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(Number(s))
}

export function formatMoney(value, currency, lang) {
  const amount = formatAmount(value, lang)
  if (amount === null) return null
  return currency ? `${amount} ${currency}` : amount
}

/** Wrap text in the quotation marks natural to the UI language: “…” in English, «…» in Arabic. */
export function quote(text, lang) {
  return lang === 'ar' ? `«${text}»` : `“${text}”`
}

export function addDays(date, days) {
  const d = new Date(date.getTime())
  d.setDate(d.getDate() + days)
  return d
}

export function formatDate(date, lang) {
  return new Intl.DateTimeFormat(DATE_LOCALE[lang], { year: 'numeric', month: 'long', day: 'numeric' }).format(date)
}

/**
 * Split `text` into segments for highlighting.
 * ranges: [{ id, start, end }] with offsets into `text` (from the backend validator).
 * Invalid or out-of-bounds ranges are ignored, never guessed.
 * Returns [{ text, ids: [...] }] covering the whole text in order.
 */
export function buildSegments(text, ranges) {
  const valid = (ranges || []).filter(
    (r) =>
      Number.isInteger(r.start) && Number.isInteger(r.end) && r.start >= 0 && r.end <= text.length && r.start < r.end,
  )
  const cuts = new Set([0, text.length])
  valid.forEach((r) => {
    cuts.add(r.start)
    cuts.add(r.end)
  })
  const points = [...cuts].sort((a, b) => a - b)
  const segments = []
  for (let i = 0; i < points.length - 1; i++) {
    const [a, b] = [points[i], points[i + 1]]
    if (a === b) continue
    const ids = valid.filter((r) => r.start <= a && r.end >= b).map((r) => r.id)
    segments.push({ text: text.slice(a, b), ids })
  }
  return segments
}

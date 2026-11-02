import { describe, expect, it } from 'vitest'
import { STRINGS } from '../i18n/strings.js'
import { addDays, buildSegments, formatAmount, formatDate, formatMoney, plural, quote } from '../lib/format.js'

describe('plural', () => {
  it('uses English singular/plural', () => {
    expect(plural('en', 'day', 1)).toBe('1 day')
    expect(plural('en', 'month', 12)).toBe('12 months')
  })
  it('uses Arabic plural categories', () => {
    expect(plural('ar', 'month', 1)).toBe('شهر واحد')
    expect(plural('ar', 'month', 2)).toBe('شهران')
    expect(plural('ar', 'month', 3)).toBe('3 أشهر')
    expect(plural('ar', 'month', 12)).toBe('12 شهرًا')
    expect(plural('ar', 'day', 7)).toBe('7 أيام')
    expect(plural('ar', 'day', 14)).toBe('14 يومًا')
  })
})

describe('amount formatting', () => {
  it('keeps the exact decimal value and uses Latin digits in both languages', () => {
    expect(formatAmount('14.49', 'en')).toBe('14.49')
    expect(formatAmount('15', 'en')).toBe('15.00')
    expect(formatAmount('1299.5', 'en')).toBe('1,299.50')
    expect(formatAmount('0.125', 'en')).toBe('0.125')
    expect(formatAmount('146.38', 'ar')).toMatch(/^146[.٫]38$/)
    expect(formatAmount('146.38', 'ar')).not.toMatch(/[٠-٩]/)
  })
  it('returns null instead of inventing a value', () => {
    expect(formatAmount(null, 'en')).toBeNull()
    expect(formatAmount(undefined, 'en')).toBeNull()
    expect(formatAmount('abc', 'en')).toBeNull()
    expect(formatMoney(null, 'USD', 'en')).toBeNull()
  })
  it('appends the currency only when stated', () => {
    expect(formatMoney('9.99', 'USD', 'en')).toBe('9.99 USD')
    expect(formatMoney('9.99', null, 'en')).toBe('9.99')
  })
})

describe('quote marks', () => {
  it('uses curly quotes in English and guillemets in Arabic', () => {
    expect(quote('text', 'en')).toBe('“text”')
    expect(quote('نص', 'ar')).toBe('«نص»')
  })
})

describe('dates', () => {
  it('formats Arabic dates with the Gregorian calendar and Latin digits', () => {
    const d = addDays(new Date(2026, 9, 29), 14)
    expect(formatDate(d, 'en')).toBe('November 12, 2026')
    const ar = formatDate(d, 'ar')
    expect(ar).toContain('2026')
    expect(ar).toContain('12')
    expect(ar).not.toMatch(/[٠-٩]/)
  })
})

describe('buildSegments', () => {
  it('splits text around ranges and keeps all text', () => {
    const text = 'abcdefghij'
    const segs = buildSegments(text, [
      { id: 'a', start: 2, end: 5 },
      { id: 'b', start: 4, end: 8 },
    ])
    expect(segs.map((s) => s.text).join('')).toBe(text)
    expect(segs).toEqual([
      { text: 'ab', ids: [] },
      { text: 'cd', ids: ['a'] },
      { text: 'e', ids: ['a', 'b'] },
      { text: 'fgh', ids: ['b'] },
      { text: 'ij', ids: [] },
    ])
  })
  it('ignores invalid or out-of-range offsets', () => {
    const segs = buildSegments('short', [
      { id: 'x', start: 2, end: 99 },
      { id: 'y', start: null, end: 3 },
      { id: 'z', start: 3, end: 3 },
    ])
    expect(segs).toEqual([{ text: 'short', ids: [] }])
  })
})

describe('translations', () => {
  const keysOf = (obj, prefix = '') =>
    Object.entries(obj).flatMap(([k, v]) =>
      v && typeof v === 'object' && !Array.isArray(v) ? keysOf(v, `${prefix}${k}.`) : [`${prefix}${k}`],
    )
  it('English and Arabic define the same keys (except Arabic-only plural forms)', () => {
    const pluralForms = /(^|\.)units\./ // Arabic has extra plural categories (zero/two/few/many)
    const en = new Set(keysOf(STRINGS.en).filter((k) => !pluralForms.test(k)))
    const ar = new Set(keysOf(STRINGS.ar).filter((k) => !pluralForms.test(k)))
    expect([...en].filter((k) => !ar.has(k))).toEqual([])
    expect([...ar].filter((k) => !en.has(k))).toEqual([])
  })
})

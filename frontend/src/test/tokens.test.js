// Verifies the real design tokens in index.css: palette compliance and WCAG contrast in both themes.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

// Read the real stylesheet from disk (Vitest runs with css: false, so ?raw imports are empty;
// under jsdom import.meta.url is not a file URL). Vitest runs from the frontend root.
const css = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')

function parseTokens(block) {
  const tokens = {}
  for (const [, name, r, g, b] of block.matchAll(/--c-([a-z-]+):\s*(\d+)\s+(\d+)\s+(\d+);/g)) tokens[name] = [+r, +g, +b]
  return tokens
}
const light = parseTokens(css.match(/:root\s*\{([\s\S]*?)\n\s*\}/)[1])
const dark = parseTokens(css.match(/\.dark\s*\{([\s\S]*?)\n\s*\}/)[1])

const lum = ([r, g, b]) => {
  const f = (c) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}
const contrast = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p)
  return (x + 0.05) / (y + 0.05)
}
const hex = (rgb) => '#' + rgb.map((c) => c.toString(16).padStart(2, '0')).join('').toUpperCase()

// [foreground, background, minimum]: 4.5 for text, 3 for icons/UI boundaries.
const PAIRS = [
  ['fg', 'bg', 4.5], ['fg', 'surface', 4.5], ['fg', 'subtle', 4.5],
  ['muted', 'surface', 4.5], ['muted', 'bg', 4.5], ['muted', 'subtle', 4.5],
  ['on-primary', 'primary', 4.5], ['on-primary', 'primary-hover', 4.5],
  ['link', 'surface', 4.5], ['fg', 'mark', 4.5], ['fg', 'mark-active', 4.5],
  ['sidebar-fg', 'sidebar', 4.5], ['sidebar-muted', 'sidebar', 4.5], ['sidebar-fg', 'sidebar-active', 4.5],
  ['match-fg', 'match-bg', 4.5], ['contra-fg', 'contra-bg', 4.5], ['unknown-fg', 'unknown-bg', 4.5],
  ['on-solid', 'match-solid', 3], ['on-solid', 'contra-solid', 3], ['on-solid', 'unknown-solid', 3],
  ['focus', 'surface', 3], ['focus', 'bg', 3],
]

describe.each([['light', light], ['dark', dark]])('%s theme tokens', (_, t) => {
  it.each(PAIRS)('%s on %s meets %s:1', (fg, bg, min) => {
    expect(t[fg], `missing token ${fg}`).toBeDefined()
    expect(t[bg], `missing token ${bg}`).toBeDefined()
    expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(min)
  })
})

describe('approved palette', () => {
  it('the guard itself rejects bright blue and cyan', () => {
    const isBright = ([r, g, b]) => {
      const max = Math.max(r, g, b)
      return (max - Math.min(r, g, b)) / max > 0.6 && max / 255 > 0.55
    }
    const isCyan = ([r, g, b]) => g > r + 60 && b > r + 60 && Math.abs(g - b) < 40
    expect(isBright([37, 99, 235])).toBe(true) // #2563EB
    expect(isCyan([6, 182, 212])).toBe(true) // #06B6D4 cyan
    expect(isBright([17, 29, 53]) || isCyan([17, 29, 53])).toBe(false) // approved navy
  })

  it('uses the exact approved values', () => {
    expect([hex(light.bg), hex(light.surface), hex(light.primary), hex(light.fg), hex(light.line)]).toEqual([
      '#F5F7FA', '#FFFFFF', '#111D35', '#111D35', '#DCE3ED',
    ])
    expect([hex(dark.bg), hex(dark.surface), hex(dark.primary), hex(dark.fg), hex(dark.line)]).toEqual([
      '#080F1E', '#152239', '#293F67', '#F4F6FB', '#293A54',
    ])
  })

  it('has no bright-blue or cyan brand tokens', () => {
    const brand = ['primary', 'primary-hover', 'link', 'mark', 'mark-active', 'focus', 'sidebar', 'sidebar-active']
    for (const t of [light, dark]) {
      for (const name of brand) {
        const [r, g, b] = t[name]
        const max = Math.max(r, g, b)
        const min = Math.min(r, g, b)
        const sat = max === 0 ? 0 : (max - min) / max
        const value = max / 255
        // "Bright" = saturated AND bright: #2563EB has sat 0.84 at value 0.92. Dark navy is
        // saturated in HSV terms but dark (#111D35: value 0.21), so it is not bright blue.
        expect(sat > 0.6 && value > 0.55, `${name} ${hex(t[name])} is a bright, saturated colour`).toBe(false)
        expect(g > r + 60 && b > r + 60 && Math.abs(g - b) < 40, `${name} ${hex(t[name])} is cyan-like`).toBe(false)
      }
    }
  })
})

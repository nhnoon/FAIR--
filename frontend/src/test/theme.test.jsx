import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { THEME_KEY } from '../theme/ThemeContext.jsx'
import { mockFetch, renderApp } from './helpers.jsx'

/** Minimal matchMedia stub whose "dark" preference can be flipped during a test. */
function stubSystemTheme(initialDark) {
  const listeners = new Set()
  const mql = {
    matches: initialDark,
    media: '(prefers-color-scheme: dark)',
    addEventListener: (_, fn) => listeners.add(fn),
    removeEventListener: (_, fn) => listeners.delete(fn),
  }
  vi.stubGlobal('matchMedia', vi.fn(() => mql))
  return {
    set(dark) {
      mql.matches = dark
      listeners.forEach((fn) => fn({ matches: dark }))
    },
  }
}

const html = () => document.documentElement
const control = () => screen.getByTestId('theme-control')

describe('theme: light, dark, system', () => {
  it('defaults to System and follows the OS preference, including live changes', async () => {
    const sys = stubSystemTheme(true)
    mockFetch()
    renderApp()
    expect(within(control()).getByRole('button', { name: 'Use system theme' })).toHaveAttribute('aria-pressed', 'true')
    await waitFor(() => expect(html()).toHaveClass('dark'))
    expect(html().style.colorScheme).toBe('dark')
    sys.set(false)
    await waitFor(() => expect(html()).not.toHaveClass('dark'))
  })

  it('Dark and Light override the OS and persist', async () => {
    stubSystemTheme(false)
    const user = userEvent.setup()
    mockFetch()
    renderApp()
    await user.click(within(control()).getByRole('button', { name: 'Dark theme' }))
    expect(html()).toHaveClass('dark')
    expect(window.localStorage.getItem(THEME_KEY)).toBe('dark')
    expect(within(control()).getByRole('button', { name: 'Dark theme' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(within(control()).getByRole('button', { name: 'Light theme' }))
    expect(html()).not.toHaveClass('dark')
    expect(window.localStorage.getItem(THEME_KEY)).toBe('light')
  })

  it('restores a saved preference on load', async () => {
    stubSystemTheme(false)
    window.localStorage.setItem(THEME_KEY, 'dark')
    mockFetch()
    renderApp()
    await waitFor(() => expect(html()).toHaveClass('dark'))
    expect(within(control()).getByRole('button', { name: 'Dark theme' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('ignores an invalid stored value', async () => {
    stubSystemTheme(false)
    window.localStorage.setItem(THEME_KEY, 'neon')
    mockFetch()
    renderApp()
    expect(within(control()).getByRole('button', { name: 'Use system theme' })).toHaveAttribute('aria-pressed', 'true')
    expect(html()).not.toHaveClass('dark')
  })

  it('works without matchMedia (falls back to light)', () => {
    vi.stubGlobal('matchMedia', undefined)
    mockFetch()
    renderApp()
    expect(html()).not.toHaveClass('dark')
  })

  it('keeps language, direction and inputs when the theme changes, and is labeled in Arabic', async () => {
    stubSystemTheme(false)
    const user = userEvent.setup()
    mockFetch()
    renderApp('ar')
    await user.type(screen.getByLabelText('شروط الاشتراك'), 'نص')
    await user.click(within(screen.getByRole('group', { name: 'المظهر' })).getByRole('button', { name: 'المظهر الداكن' }))
    expect(html()).toHaveClass('dark')
    expect(html()).toHaveAttribute('dir', 'rtl')
    expect(screen.getByLabelText('شروط الاشتراك')).toHaveValue('نص')
  })
})

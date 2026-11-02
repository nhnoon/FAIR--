import { useEffect, useRef } from 'react'
import { useLang } from '../i18n/LanguageContext.jsx'
import { THEMES, useTheme } from '../theme/ThemeContext.jsx'
import { FairMark, GlobeIcon, InfoIcon, ListIcon, MenuIcon, MonitorIcon, MoonIcon, SearchIcon, SunIcon, XIcon } from './icons.jsx'

export const VIEWS = ['analyze', 'results', 'about']
const NAV_ICONS = { analyze: SearchIcon, results: ListIcon, about: InfoIcon }
const THEME_ICONS = { light: SunIcon, dark: MoonIcon, system: MonitorIcon }

// System status uses neutral surfaces; only the dot carries a status colour.
const STATUS_DOT = {
  checking: 'bg-muted',
  live: 'bg-match-solid',
  replay: 'bg-unknown-solid',
  not_configured: 'bg-unknown-solid',
  disabled: 'bg-unknown-solid',
  unreachable: 'bg-contra-solid',
}

export function StatusPill({ status }) {
  const { t } = useLang()
  return (
    <span
      className="chip whitespace-nowrap bg-subtle text-fg ring-line"
      data-testid="status-pill"
      data-status={status}
      role="status"
      aria-label={`${t('status.label')}: ${t(`status.${status}`)}`}
    >
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[status]}`} />
      {t(`status.${status}`)}
    </span>
  )
}

export function ThemeControl() {
  const { t } = useLang()
  const { preference, setPreference } = useTheme()
  return (
    <div role="group" aria-label={t('theme.label')} className="inline-flex shrink-0 rounded-full border border-line bg-surface p-0.5" data-testid="theme-control">
      {THEMES.map((m) => {
        const Icon = THEME_ICONS[m]
        const active = preference === m
        return (
          <button
            key={m}
            type="button"
            onClick={() => setPreference(m)}
            aria-pressed={active}
            aria-label={t(`theme.${m}`)}
            title={t(`theme.${m}`)}
            className={`grid h-8 w-8 place-items-center rounded-full transition-colors ${
              active ? 'bg-primary text-primary-fg' : 'text-muted hover:bg-subtle hover:text-fg'
            }`}
          >
            <Icon width={15} height={15} />
          </button>
        )
      })}
    </div>
  )
}

function Brand() {
  const { t } = useLang()
  return (
    <div className="flex items-center gap-3 px-2">
      <FairMark size={34} />
      <div className="min-w-0 leading-tight">
        <p className="flex items-baseline gap-1.5">
          <span className="font-bold tracking-[0.06em] text-sidebar-fg">{t('brand.name')}</span>
          <span aria-hidden="true" className="text-sidebar-muted">|</span>
          <span lang="ar" className="font-arabic font-semibold text-sidebar-fg">
            {t('brand.arabicName')}
          </span>
        </p>
        <p className="truncate text-xs text-sidebar-muted">{t('brand.tagline')}</p>
      </div>
    </div>
  )
}

function NavList({ view, onNavigate, hasResult, firstRef }) {
  const { t } = useLang()
  return (
    <ul className="space-y-1">
      {VIEWS.map((v, i) => {
        const Icon = NAV_ICONS[v]
        const locked = v === 'results' && !hasResult
        const current = view === v
        return (
          <li key={v}>
            <button
              ref={i === 0 ? firstRef : undefined}
              type="button"
              onClick={() => !locked && onNavigate(v)}
              aria-current={current ? 'page' : undefined}
              aria-disabled={locked ? 'true' : undefined}
              title={locked ? t('nav.resultsLocked') : undefined}
              className={`flex min-h-[44px] w-full items-center gap-3 rounded-xl px-3 text-start text-sm font-medium transition-colors ${
                current
                  ? 'bg-sidebar-active text-sidebar-fg ring-1 ring-sidebar-fg/15'
                  : locked
                    ? 'cursor-not-allowed text-sidebar-muted/70'
                    : 'text-sidebar-muted hover:bg-sidebar-active/60 hover:text-sidebar-fg'
              }`}
            >
              <Icon width={18} height={18} className="shrink-0" />
              <span className="flex-1 py-1.5">
                <span className="block">{t(`nav.${v}`)}</span>
                {locked ? <span className="block text-[11px] font-normal leading-snug">{t('nav.resultsLocked')}</span> : null}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

function SidebarBody({ view, onNavigate, hasResult, firstRef }) {
  const { t } = useLang()
  return (
    <div className="flex h-full flex-col gap-8 border-e border-sidebar-fg/10 bg-sidebar px-3 py-5">
      <Brand />
      <nav aria-label={t('nav.label')} className="flex-1">
        <NavList view={view} onNavigate={onNavigate} hasResult={hasResult} firstRef={firstRef} />
      </nav>
      <p className="px-2 text-xs leading-relaxed text-sidebar-muted">{t('nav.disclaimer')}</p>
    </div>
  )
}

function MobileDrawer({ open, onClose, menuButtonRef, ...navProps }) {
  const { t } = useLang()
  const panelRef = useRef(null)
  const firstRef = useRef(null)
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  // Depends on `open` only, so re-renders never move focus while the drawer is open.
  useEffect(() => {
    if (!open) return
    firstRef.current?.focus()
    const menuButton = menuButtonRef.current
    const onKey = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onCloseRef.current()
        return
      }
      if (e.key !== 'Tab') return
      const nodes = panelRef.current?.querySelectorAll('button:not([disabled])')
      if (!nodes?.length) return
      const first = nodes[0]
      const last = nodes[nodes.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      menuButton?.focus()
    }
  }, [open, menuButtonRef])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 lg:hidden">
      <div className="absolute inset-0 bg-bg/70" aria-hidden="true" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={t('nav.label')}
        className="absolute inset-y-0 start-0 flex w-72 max-w-[85vw] flex-col shadow-lift"
      >
        <SidebarBody
          {...navProps}
          firstRef={firstRef}
          onNavigate={(v) => {
            navProps.onNavigate(v)
            onClose()
          }}
        />
        <button
          type="button"
          onClick={onClose}
          aria-label={t('nav.close')}
          className="absolute end-2 top-4 grid h-10 w-10 place-items-center rounded-lg text-sidebar-muted hover:bg-sidebar-active hover:text-sidebar-fg"
        >
          <XIcon width={18} height={18} />
        </button>
      </div>
    </div>
  )
}

export default function AppShell({ view, onNavigate, hasResult, status, drawerOpen, setDrawerOpen, children }) {
  const { t, setLang } = useLang()
  const menuButtonRef = useRef(null)
  const target = t('lang.switchToLang')
  const mainRef = useRef(null)

  return (
    <div className="min-h-screen bg-bg">
      <a
        href="#workspace"
        onClick={(e) => {
          e.preventDefault()
          mainRef.current?.focus()
        }}
        className="sr-only focus:not-sr-only focus:fixed focus:start-4 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-4 focus:py-2 focus:text-fg"
      >
        {t('nav.skip')}
      </a>

      {/* Desktop sidebar: left in English, mirrored to the right in Arabic via logical `start`. */}
      <aside className="fixed inset-y-0 start-0 z-30 hidden w-64 lg:block" data-testid="sidebar">
        <SidebarBody view={view} onNavigate={onNavigate} hasResult={hasResult} />
      </aside>

      <MobileDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        menuButtonRef={menuButtonRef}
        view={view}
        onNavigate={onNavigate}
        hasResult={hasResult}
      />

      <div className="lg:ps-64">
        <header className="sticky top-0 z-20 border-b border-line bg-surface">
          {/* One status pill: inline on wider screens, wrapped onto its own row on phones. */}
          <div className="mx-auto flex min-h-[56px] max-w-5xl flex-wrap items-center gap-x-2 gap-y-1.5 px-4 py-2 sm:flex-nowrap sm:gap-x-3 sm:px-6">
            <button
              ref={menuButtonRef}
              type="button"
              onClick={() => setDrawerOpen(true)}
              aria-label={t('nav.open')}
              aria-expanded={drawerOpen}
              className="-ms-2 grid h-10 w-10 place-items-center rounded-lg text-fg hover:bg-subtle lg:hidden"
            >
              <MenuIcon width={20} height={20} />
            </button>
            <p className="min-w-0 flex-1 truncate text-sm font-semibold text-fg" data-testid="workspace-title">
              {t(`nav.${view}`)}
            </p>
            <span className="order-last w-full sm:order-none sm:w-auto">
              <StatusPill status={status} />
            </span>
            <ThemeControl />
            <button
              type="button"
              onClick={() => setLang(target)}
              aria-label={t('lang.switchAria')}
              className="inline-flex min-h-[36px] shrink-0 items-center gap-1.5 rounded-full border border-line bg-surface px-3 text-sm font-semibold text-fg hover:bg-subtle"
            >
              <GlobeIcon width={15} height={15} />
              <span lang={target}>{t('lang.switchTo')}</span>
            </button>
          </div>
        </header>

        <main id="workspace" ref={mainRef} tabIndex={-1} className="mx-auto max-w-5xl px-4 py-6 focus:outline-none sm:px-6 sm:py-8">
          {children}
        </main>
      </div>
    </div>
  )
}

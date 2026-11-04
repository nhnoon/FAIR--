import { useRef } from 'react'
import { useLang } from '../i18n/LanguageContext.jsx'
import { THEMES, useTheme } from '../theme/ThemeContext.jsx'
import { FairMark, MonitorIcon, MoonIcon, SunIcon } from './icons.jsx'

export const VIEWS = ['home', 'analyze', 'results', 'about']
const THEME_ICONS = { light: SunIcon, dark: MoonIcon, system: MonitorIcon }

// The top bar names one state only: a replay must never pass for a live product.
// Every other state is a note under the form (AvailabilityNote).
export function StatusPill({ status }) {
  const { t } = useLang()
  if (status !== 'replay') return null
  return (
    <span className="chip whitespace-nowrap text-muted" data-testid="status-pill" data-status={status} role="status" aria-label={`${t('status.label')}: ${t(`status.${status}`)}`}>
      <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-unknown-solid" />
      {t(`status.${status}`)}
    </span>
  )
}

export function ThemeControl() {
  const { t } = useLang()
  const { preference, setPreference } = useTheme()
  return (
    <div role="group" aria-label={t('theme.label')} className="inline-flex shrink-0 rounded-lg bg-subtle p-0.5" data-testid="theme-control">
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
            className={`grid h-8 w-8 place-items-center rounded-md transition-colors ${active ? 'bg-surface text-fg shadow-soft' : 'text-muted hover:text-fg'}`}
          >
            <Icon width={15} height={15} />
          </button>
        )
      })}
    </div>
  )
}

function Brand({ onHome, footer }) {
  const { t } = useLang()
  return (
    <button type="button" onClick={onHome} className="inline-flex min-h-[44px] shrink-0 items-center gap-2 rounded-lg" aria-label={t('nav.home')} data-testid={footer ? undefined : 'brand-home'}>
      <FairMark size={26} />
      <span className="text-[17px] font-bold tracking-tight text-fg">{t('brand.name')}</span>
      <span lang="ar" className="font-arabic text-sm text-muted">
        {t('brand.arabicName')}
      </span>
    </button>
  )
}

function LanguageButton() {
  const { t, setLang } = useLang()
  const target = t('lang.switchToLang')
  return (
    <button type="button" onClick={() => setLang(target)} aria-label={t('lang.switchAria')} className="inline-flex min-h-[40px] shrink-0 items-center rounded-lg px-2.5 text-sm font-medium text-fg hover:bg-subtle">
      <span lang={target}>{t('lang.switchTo')}</span>
    </button>
  )
}

export function Footer({ onNavigate }) {
  const { t } = useLang()
  return (
    <footer className="border-t border-line bg-surface">
      <div className="page flex flex-wrap items-center justify-between gap-x-6 gap-y-3 py-5">
        <p className="min-w-0 text-xs text-muted">{t('nav.disclaimer')}</p>
        <div className="flex items-center gap-4">
          <button type="button" className="inline-flex min-h-[40px] items-center rounded text-sm font-medium text-fg underline-offset-4 hover:underline" onClick={() => onNavigate('about')}>
            {t('nav.about')}
          </button>
          <ThemeControl />
        </div>
      </div>
    </footer>
  )
}

export default function AppShell({ view, onNavigate, hasResult, status, children }) {
  const { t } = useLang()
  const mainRef = useRef(null)

  return (
    <div className="flex min-h-screen flex-col bg-bg">
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

      <header className="sticky top-0 z-20 border-b border-line bg-surface">
        <div className="page flex min-h-[64px] flex-wrap items-center gap-x-3 gap-y-1 py-2 sm:gap-x-4">
          <Brand onHome={() => onNavigate('home')} />
          <p className="sr-only" data-testid="workspace-title">
            {t(`nav.${view}`)}
          </p>
          {status === 'replay' ? (
            <span className="order-last w-full sm:order-none sm:w-auto">
              <StatusPill status={status} />
            </span>
          ) : null}
          <span className="flex-1" />
          <nav aria-label={t('nav.label')} className="flex items-center gap-1 sm:gap-2" data-testid="primary-nav">
            {hasResult && view !== 'results' ? (
              <button type="button" onClick={() => onNavigate('results')} className="hidden min-h-[40px] items-center rounded-lg px-2.5 text-sm font-medium text-fg hover:bg-subtle sm:inline-flex">
                {t('nav.results')}
              </button>
            ) : null}
            {view === 'results' && hasResult ? <span className="sr-only" aria-current="page">{t('nav.results')}</span> : null}
            <LanguageButton />
            <button type="button" onClick={() => onNavigate('analyze')} aria-current={view === 'analyze' ? 'page' : undefined} className="btn-primary min-h-[40px] whitespace-nowrap px-3.5">
              {t('nav.analyze')}
            </button>
          </nav>
        </div>
      </header>

      <main id="workspace" ref={mainRef} tabIndex={-1} className="flex w-full flex-1 flex-col focus:outline-none">
        <div className="flex-1">{children}</div>
      </main>
      <Footer onNavigate={onNavigate} />
    </div>
  )
}

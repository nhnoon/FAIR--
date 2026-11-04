import { forwardRef } from 'react'
import { SAVED_EXAMPLES } from '../examples/index.js'
import { useLang } from '../i18n/LanguageContext.jsx'
import { ArrowIcon } from './icons.jsx'
import ResultCard from './ResultCard.jsx'

const HomeView = forwardRef(function HomeView({ onStart, onOpenExample }, headingRef) {
  const { t, lang } = useLang()
  const example = SAVED_EXAMPLES.find((ex) => ex.id === (lang === 'ar' ? 'FAIR-026' : 'FAIR-011'))
  return (
    <div className="bg-ink text-ink-fg" data-testid="view-home">
      <div className="page grid items-center gap-10 py-12 lg:min-h-[calc(100vh-4rem)] lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)] lg:gap-16 lg:py-14">
        <div className="min-w-0">
          <h1 ref={headingRef} tabIndex={-1} className="text-4xl font-semibold leading-[1.1] tracking-tight [text-wrap:balance] focus:outline-none sm:text-6xl">
            {t('home.title')}
          </h1>
          <p className="mt-5 max-w-md text-lg text-ink-muted sm:text-xl">{t('home.body')}</p>
          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            <button type="button" className="btn btn-cta bg-ink-fg font-semibold text-ink hover:bg-ink-fg/90" onClick={onStart}>
              {t('nav.analyze')}
              <ArrowIcon width={17} height={17} />
            </button>
            <button type="button" className="inline-flex min-h-[44px] items-center rounded text-sm font-medium underline underline-offset-4" onClick={() => onOpenExample(example.id)}>
              {t('home.openFull')}
            </button>
          </div>
        </div>
        <div className="min-w-0" data-testid="product-proof">
          <ResultCard compact data={example.response} expectation={example.expectation} />
          <p className="mt-3 text-xs text-ink-muted" data-testid="proof-label">
            {t('home.proofLabel')}
          </p>
        </div>
      </div>
    </div>
  )
})

export default HomeView

import { forwardRef } from 'react'
import { useLang } from '../i18n/LanguageContext.jsx'

function Block({ title, items }) {
  return (
    <section className="grid gap-3 border-t border-line pt-6 sm:grid-cols-[9rem_minmax(0,1fr)] sm:gap-6">
      <h2 className="text-lg font-semibold text-fg">{title}</h2>
      <ul className="space-y-3 leading-relaxed text-muted">
        {items.map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ul>
    </section>
  )
}

const AboutView = forwardRef(function AboutView(_, headingRef) {
  const { t } = useLang()
  return (
    <div className="page max-w-3xl space-y-8 py-10 sm:py-14">
      <div>
        <h1 ref={headingRef} tabIndex={-1} className="text-3xl font-semibold tracking-tight text-fg focus:outline-none">
          {t('about.title')}
        </h1>
        <p className="mt-3 leading-relaxed text-muted">{t('about.intro')}</p>
      </div>
      <Block title={t('about.howTitle')} items={t('about.how')} />
      <Block title={t('about.limitsTitle')} items={t('about.limits')} />
      <Block title={t('about.privacyTitle')} items={t('about.privacy')} />
      <p className="border-t border-line pt-6 text-sm text-muted">{t('about.advice')}</p>
    </div>
  )
})

export default AboutView

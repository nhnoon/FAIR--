import { forwardRef } from 'react'
import { useLang } from '../i18n/LanguageContext.jsx'

function Block({ title, items }) {
  return (
    <section className="card p-5 sm:p-6">
      <h2 className="section-title">{title}</h2>
      <ul className="mt-3 list-disc space-y-2 ps-5 text-sm leading-relaxed text-muted">
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
    <div className="max-w-3xl space-y-5">
      <div>
        <h1 ref={headingRef} tabIndex={-1} className="text-2xl font-bold text-fg focus:outline-none">
          {t('about.title')}
        </h1>
        <p className="mt-2 leading-relaxed text-muted">{t('about.intro')}</p>
      </div>
      <Block title={t('about.howTitle')} items={t('about.how')} />
      <Block title={t('about.limitsTitle')} items={t('about.limits')} />
      <Block title={t('about.privacyTitle')} items={t('about.privacy')} />
      <div className="space-y-1 text-xs text-muted">
        <p className="font-medium text-muted">{t('about.advice')}</p>
        <p>{t('about.built')}</p>
      </div>
    </div>
  )
})

export default AboutView

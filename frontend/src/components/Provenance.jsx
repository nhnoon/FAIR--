import { useLang } from '../i18n/LanguageContext.jsx'

// Where a piece of information comes from. Every finding in Results carries one of these:
// a small mark and a word, quiet enough to sit beside a finding without competing with it.
const KINDS = {
  terms: 'bg-link', // verified quote from the offer text
  ai: 'border border-muted', // model interpretation
  calc: 'bg-fg', // deterministic Decimal code
  assumption: 'bg-unknown-solid',
  unknown: 'border border-dashed border-muted',
}

export function ProvenanceTag({ kind }) {
  const { t } = useLang()
  return (
    <span className="chip text-muted" data-provenance={kind}>
      <span aria-hidden="true" className={`h-2 w-2 shrink-0 rounded-full ${KINDS[kind]}`} />
      {t(`provenance.${kind}`)}
    </span>
  )
}

export function ProvenanceLegend() {
  const { t } = useLang()
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted" data-testid="provenance-legend">
      {Object.keys(KINDS).map((k) => (
        <ProvenanceTag key={k} kind={k} />
      ))}
      <span className="sr-only">{t('provenance.legend')}</span>
    </div>
  )
}

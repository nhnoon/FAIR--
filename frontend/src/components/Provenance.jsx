import { useLang } from '../i18n/LanguageContext.jsx'
import { AlertIcon, CalculatorIcon, CheckIcon, QuestionIcon, SearchIcon } from './icons.jsx'

// Where a piece of information comes from. Every finding in Results carries one of these.
const KINDS = {
  terms: { Icon: CheckIcon, cls: 'bg-subtle text-fg ring-line' }, // verified quote from the offer text
  ai: { Icon: SearchIcon, cls: 'bg-surface text-muted ring-0 border border-dashed border-muted/60' }, // model interpretation
  calc: { Icon: CalculatorIcon, cls: 'bg-subtle text-fg ring-line' }, // deterministic Decimal code
  assumption: { Icon: AlertIcon, cls: 'bg-unknown-bg text-unknown-fg ring-unknown-line' },
  unknown: { Icon: QuestionIcon, cls: 'bg-surface text-muted ring-line' },
}

export function ProvenanceTag({ kind }) {
  const { t } = useLang()
  const k = KINDS[kind]
  return (
    <span className={`chip ${k.cls}`} data-provenance={kind}>
      <k.Icon width={11} height={11} />
      {t(`provenance.${kind}`)}
    </span>
  )
}

export function ProvenanceLegend() {
  const { t } = useLang()
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted" data-testid="provenance-legend">
      <span className="font-medium">{t('provenance.legend')}:</span>
      {Object.keys(KINDS).map((k) => (
        <ProvenanceTag key={k} kind={k} />
      ))}
    </div>
  )
}

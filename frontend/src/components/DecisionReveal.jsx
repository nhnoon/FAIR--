import { useMemo, useState } from 'react'
import { useLang } from '../i18n/LanguageContext.jsx'
import { collectEvidence, factEvidenceId, sourceFieldEvidenceId } from '../lib/evidence.js'
import { formatMoney, quote } from '../lib/format.js'
import Chapter from './Chapter.jsx'
import { assumptionText } from './FutureReceipt.jsx'
import { ProvenanceTag } from './Provenance.jsx'

const LONG_HORIZON = 12

/**
 * Up to three choices, each priced only from totals the backend already calculated. No arithmetic here.
 * "Miss the deadline" exists only for a trial: its first charge is the one-month total of keeping the plan.
 */
export function buildChoices(decision) {
  if (!decision) return []
  const keep = decision.continue_path
  const cancel = decision.cancel_path
  const total = (path, months) => path?.horizons?.find((h) => h.months === months && h.status !== 'unavailable')?.total ?? null
  const lines = (path, months) => path?.horizons?.find((h) => h.months === months)?.lines ?? []
  const choices = []
  if (total(keep, LONG_HORIZON) != null) {
    choices.push({ key: 'keep', amount: total(keep, LONG_HORIZON), status: keep.status, codes: keep.assumption_codes, lines: lines(keep, LONG_HORIZON) })
  }
  if (cancel?.status === 'conditional' && total(cancel, LONG_HORIZON) != null) {
    choices.push({ key: 'cancel', amount: total(cancel, LONG_HORIZON), status: 'conditional', codes: cancel.assumption_codes, lines: lines(cancel, LONG_HORIZON), deadline: true })
    if (cancel.deadline?.kind === 'trial_end' && total(keep, 1) != null) {
      // Its fixed wording covers the deadline; an amount the total leaves out still has to be said.
      const left = (keep.assumption_codes || []).filter((code) => code === 'amount_not_counted')
      choices.push({ key: 'miss', amount: total(keep, 1), status: 'conditional', codes: left, lines: lines(keep, 1), deadline: true })
    }
  }
  return choices
}

function Ledger({ title, kind, testId, children }) {
  return (
    <div className="min-w-0" data-testid={testId}>
      <h3 className="text-sm font-medium text-fg">{title}</h3>
      <div className="mt-0.5 sr-only">
        <ProvenanceTag kind={kind} />
      </div>
      <ul className="mt-2 space-y-2 text-sm text-fg">{children}</ul>
    </div>
  )
}

// Shown only with a verified contradiction and at least two priced choices. It does not claim that the
// contradicted sentence caused the amounts: it sets the belief beside what each choice costs under the terms.
export function canReveal(data) {
  return !!(data.claims || []).find((c) => c.verdict === 'CONTRADICTION' && !c.downgraded && c.evidence?.verified) && buildChoices(data.decision).length >= 2
}

export default function DecisionReveal({ data, onShowEvidence }) {
  const { t, lang } = useLang()
  const choices = useMemo(() => buildChoices(data.decision), [data.decision])
  const [selected, setSelected] = useState('keep')
  const verifiedById = useMemo(() => new Map(collectEvidence(data).verified.map((it) => [it.id, it])), [data])
  const claim = (data.claims || []).find((c) => c.verdict === 'CONTRADICTION' && !c.downgraded && c.evidence?.verified)
  if (!claim || choices.length < 2) return null

  const money = (v) => formatMoney(v, data.cost.currency, lang)
  const choice = choices.find((c) => c.key === selected) || choices[0]
  const sourceIds = [...new Set([...choice.lines.map((ln) => sourceFieldEvidenceId(ln.source_field)), ...(choice.deadline ? [factEvidenceId('cancel_by')] : [])])]
  const sources = sourceIds.map((id) => verifiedById.get(id)).filter(Boolean)
  // One entry per passage: a quote inside a longer listed quote adds nothing.
  const unique = [...new Map(sources.map((it) => [it.evidence.quote, it])).values()]
  const quotes = unique.filter((it) => !unique.some((o) => o !== it && o.evidence.quote.includes(it.evidence.quote)))
  const unsettled = (data.claims || []).filter((c) => c.verdict === 'UNKNOWN')

  return (
    <Chapter id="reveal-heading" title={t('reveal.title')} testId="decision-reveal">
      <h3 className="text-sm font-medium text-fg" id="reveal-choices">
        {t('reveal.question')}
      </h3>
      <div role="group" aria-labelledby="reveal-choices" className={`mt-3 grid gap-3 ${choices.length === 3 ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
        {choices.map((c) => (
          <button
            key={c.key}
            type="button"
            aria-pressed={choice.key === c.key}
            onClick={() => setSelected(c.key)}
            data-testid={`reveal-choice-${c.key}`}
            className={`min-w-0 rounded-2xl border p-4 text-start transition-colors ${choice.key === c.key ? 'border-focus bg-mark ring-1 ring-focus' : 'border-line hover:bg-subtle'}`}
          >
            <span className="block text-sm font-medium">{t(`reveal.choices.${c.key}.label`)}</span>
            <span className="mt-0.5 block text-xs text-muted">{t(`reveal.choices.${c.key}.period`)}</span>
            <bdi className="mt-2 block text-lg font-semibold tabular-nums" data-testid={`reveal-amount-${c.key}`}>
              {c.key === 'miss' ? t('reveal.atLeast', { amount: money(c.amount) }) : money(c.amount)}
            </bdi>
            <span className={`mt-1 block text-xs font-medium ${c.status === 'conditional' ? 'text-unknown-fg' : 'text-muted'}`}>{t(`cost.status.${c.status}`)}</span>
          </button>
        ))}
      </div>
      <div className="mt-2">
        <ProvenanceTag kind="calc" />
      </div>

      <div className="mt-6 grid gap-6 md:grid-cols-3" aria-live="polite">
        <Ledger title={t('reveal.verified')} kind="terms" testId="reveal-verified">
          {quotes.map((it) => (
            <li key={it.id} className="min-w-0">
              <p dir="auto" className="break-words">
                {quote(it.evidence.quote, lang)}
              </p>
              <button type="button" className="text-link-btn mt-0.5 flex" onClick={() => onShowEvidence(it.id)}>
                {t('reveal.seeQuote')}
              </button>
            </li>
          ))}
        </Ledger>
        <Ledger title={t('reveal.assumed')} kind="assumption" testId="reveal-assumed">
          {choice.key === 'miss' ? <li>{t('reveal.choices.miss.assumption')}</li> : null}
          {choice.codes.map((code) => (
            <li key={code}>{assumptionText(t, lang, code)}</li>
          ))}
        </Ledger>
        <Ledger title={t('reveal.unknown')} kind="unknown" testId="reveal-unknown">
          {choice.key === 'miss' ? <li>{t('reveal.choices.miss.unknown')}</li> : null}
          {unsettled.map((c) => (
            <li key={c.id} dir="auto" className="break-words">
              {quote(c.text, lang)}
            </li>
          ))}
          {choice.key !== 'miss' && !unsettled.length ? <li className="text-muted">{t('reveal.noUnknown')}</li> : null}
        </Ledger>
      </div>
    </Chapter>
  )
}

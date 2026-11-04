import { useLang } from '../i18n/LanguageContext.jsx'
import { decidingEvidenceId, decidingQuote, overallVerdict } from '../lib/evidence.js'
import { formatMoney, plural, quote } from '../lib/format.js'
import { CheckIcon, QuestionIcon, XIcon } from './icons.jsx'

const STYLE = {
  MATCH: { pill: 'bg-match-solid text-on-solid', hl: 'bg-hl-match', bar: 'bg-match-solid', Icon: CheckIcon },
  CONTRADICTION: { pill: 'bg-contra-solid text-on-solid', hl: 'bg-hl-contra', bar: 'bg-contra-solid', Icon: XIcon },
  UNKNOWN: { pill: 'bg-unknown-solid text-on-solid', hl: 'bg-hl-unknown', bar: 'bg-unknown-solid', Icon: QuestionIcon },
}

const LONG_HORIZON = 12

/** The money, read from backend totals only. A scenario is never drawn like an established total. */
function CostSummary({ data }) {
  const { t, lang } = useLang()
  const { cost, decision } = data
  const money = (v) => formatMoney(v, cost.currency, lang)
  const withheld = cost.withheld || []
  const horizon = (path) => path?.horizons?.find((h) => h.months === LONG_HORIZON && h.status !== 'unavailable' && h.total != null)
  const keep = horizon(decision?.continue_path)
  const cancel = decision?.cancel_path?.status === 'conditional' ? horizon(decision.cancel_path) : null
  const hasNext = cost.first_paid_charge_day != null && cost.first_paid_charge_amount != null

  if (withheld.length) {
    const first = withheld[0]
    return (
      <div data-testid="primary-withheld">
        <p className="font-medium text-fg">{t('result.noTotal')}</p>
        <p className="mt-1 text-sm text-muted">{t(`receipt.withheld.${first.code}`, { amount: first.amount != null ? money(first.amount) : '', rate: first.rate ?? '' })}</p>
        {data.extracted_terms.recurring_price != null ? (
          <p className="mt-2 text-sm text-fg">
            <bdi>{t('receipt.withheld.statedPrice', { amount: money(data.extracted_terms.recurring_price) })}</bdi>
          </p>
        ) : null}
      </div>
    )
  }
  if (!keep && !hasNext) return <p className="text-sm text-muted" data-testid="primary-no-total">{t('result.noEstablished')}</p>

  return (
    <dl className="space-y-4">
      {keep ? (
        <div data-testid="primary-keep">
          <dt className="text-sm text-muted">{t('result.keepFor', { months: plural(lang, 'month', LONG_HORIZON) })}</dt>
          <dd className="mt-0.5 text-3xl font-semibold tabular-nums tracking-tight text-fg">
            <bdi>{money(keep.total)}</bdi>
          </dd>
          <dd className="text-xs text-muted">{t(`cost.status.${keep.status}`)}</dd>
        </div>
      ) : null}
      {hasNext ? (
        <div data-testid="primary-next">
          <dt className="text-sm text-muted">{t('cost.firstCharge')}</dt>
          <dd className="mt-0.5 font-medium text-fg">
            <bdi>{cost.first_paid_charge_day > 0 ? t('cost.firstChargeOn', { amount: money(cost.first_paid_charge_amount), day: cost.first_paid_charge_day }) : t('cost.firstChargeImmediate', { amount: money(cost.first_paid_charge_amount) })}</bdi>
          </dd>
        </div>
      ) : null}
      {cancel ? (
        <div className="border-t border-line pt-3 text-sm" data-testid="primary-cancel">
          <dt className="text-muted">{t('result.ifCancel')}</dt>
          <dd className="mt-0.5 text-fg">
            <bdi className="font-medium">{money(cancel.total)}</bdi> · {t('cost.status.conditional')}
          </dd>
          <dd className="mt-0.5 text-xs text-muted">{t('result.cancelCaveat')}</dd>
        </div>
      ) : null}
    </dl>
  )
}

/** The answer. Verdict, reason, the deciding clause and the money, on one screen. */
export default function ResultCard({ data, expectation, compact, onShowEvidence, actions }) {
  const { t, lang } = useLang()
  const verdict = overallVerdict(data)
  const s = STYLE[verdict]
  const evidence = decidingQuote(data)
  const unsettled = (data.claims || []).filter((c) => c.verdict === 'UNKNOWN')

  return (
    <div className={`overflow-hidden rounded-3xl border border-line bg-surface text-fg shadow-lift ${compact ? '' : 'grid lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]'}`}>
      <div className={`min-w-0 ${compact ? 'p-6' : 'p-6 sm:p-8'}`}>
        <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-semibold ${s.pill}`}>
          <s.Icon width={14} height={14} strokeWidth={3} />
          {t(`verdict.${verdict}.tag`)}
        </span>
        <h2 id={compact ? undefined : 'verdict-heading'} className={`mt-3 font-semibold leading-tight tracking-tight ${compact ? 'text-xl' : 'text-2xl sm:text-3xl'}`}>
          {t(`verdict.${verdict}.headline`)}
        </h2>
        {compact ? null : (
          <>
            <p className="mt-2 max-w-2xl break-words text-[17px] leading-relaxed text-fg" lang={lang}>
              {data.explanation[lang]}
            </p>
            <p className="mt-1 text-xs text-muted">{t('provenance.ai')}</p>
          </>
        )}

        <div className={`${compact ? 'mt-4' : 'mt-5'} space-y-3`}>
          <p className="break-words text-sm text-muted">
            <span className="font-medium">{t('reveal.believed')}: </span>
            <span dir="auto" className="text-fg">
              {quote(expectation, lang)}
            </span>
          </p>
          <div className="relative overflow-hidden rounded-2xl bg-paper p-4 ps-5 text-paper-fg">
            <span aria-hidden="true" className={`absolute inset-y-0 start-0 w-1 ${s.bar}`} />
            <p className="text-xs font-medium text-paper-muted">{t('reveal.termsSay')}</p>
            {evidence ? (
              <>
                <p dir="auto" className="mt-1 break-words text-[17px] font-medium leading-relaxed">
                  <mark className={`box-decoration-clone rounded px-1 text-paper-fg ${s.hl}`}>{quote(evidence, lang)}</mark>
                </p>
                {onShowEvidence ? (
                  <button type="button" className="mt-1 inline-flex min-h-[32px] items-center rounded text-xs font-medium underline underline-offset-4" onClick={() => onShowEvidence(decidingEvidenceId(data))}>
                    {t('reveal.seeQuote')}
                  </button>
                ) : null}
              </>
            ) : (
              <p className="mt-1 text-[17px] text-paper-muted">{t('mirror.noEvidence')}</p>
            )}
          </div>
        </div>

        {data.verdict_downgraded && !compact ? (
          <p className="mt-3 text-sm text-unknown-fg" data-testid="downgraded">
            {t('verdict.downgraded', { verdict: t(`verdict.words.${data.model_verdict}`) })}
          </p>
        ) : null}
      </div>

      <div className={`flex min-w-0 flex-col gap-4 bg-subtle/60 ${compact ? 'border-t border-line p-6' : 'border-t border-line p-6 sm:p-8 lg:border-s lg:border-t-0'}`}>
        <div>
          <h3 className="mb-3 text-sm font-semibold text-fg">{t('result.costTitle')}</h3>
          <CostSummary data={data} />
        </div>
        {unsettled.length && !compact ? (
          <div className="border-t border-line pt-3 text-sm" data-testid="primary-open">
            <p className="text-muted">{t('result.stillOpen')}</p>
            <ul className="mt-0.5 space-y-1 text-fg">
              {unsettled.slice(0, 2).map((c) => (
                <li key={c.id} dir="auto" className="break-words">
                  {quote(c.text, lang)}
                </li>
              ))}
            </ul>
            {unsettled.length > 2 ? <p className="mt-1 text-xs text-muted">{t('result.andMore', { n: unsettled.length - 2 })}</p> : null}
          </div>
        ) : null}
        {actions ? <div className="mt-auto flex flex-wrap gap-2 pt-1">{actions}</div> : null}
      </div>
    </div>
  )
}

import { useMemo, useState } from 'react'
import { lookup, useLang } from '../i18n/LanguageContext.jsx'
import { collectEvidence, factEvidenceId, sourceFieldEvidenceId } from '../lib/evidence.js'
import { addDays, formatDate, formatMoney, plural, pluralFrom, quote } from '../lib/format.js'
import Chapter from './Chapter.jsx'
import { ProvenanceTag } from './Provenance.jsx'
import { AlertIcon, CheckIcon, MinusIcon } from './icons.jsx'

// Every amount shown here comes from the backend (Decimal). React only formats it.
const HORIZONS = [1, 3, 12]
const STATUS = {
  complete: { cls: 'text-muted', Icon: CheckIcon, key: 'cost.status.complete' },
  conditional: { cls: 'text-unknown-fg', Icon: AlertIcon, key: 'cost.status.conditional' },
  unavailable: { cls: 'text-muted', Icon: MinusIcon, key: 'cost.status.unavailable' },
}

function StatusChip({ status }) {
  const { t } = useLang()
  const s = STATUS[status]
  return (
    <span className={`chip ${s.cls}`}>
      <s.Icon width={12} height={12} />
      {t(s.key)}
    </span>
  )
}

function SourceButton({ evidenceId, label, onShowEvidence }) {
  const { t } = useLang()
  if (!evidenceId) return null
  return (
    <button type="button" className="text-link-btn" onClick={() => onShowEvidence(evidenceId)} aria-label={t('receipt.showEvidence', { item: label })}>
      {t('provenance.terms')}
    </button>
  )
}

export function assumptionText(t, lang, code) {
  return lookup(lang, `receipt.assumptionText.${code}`) ? t(`receipt.assumptionText.${code}`) : t(`cost.assumptionText.${code}`)
}

function Deadline({ deadline, verifiedIds, onShowEvidence, today }) {
  const { t, lang } = useLang()
  const notice = deadline.notice ? pluralFrom(lang, lookup(lang, `receipt.units.${deadline.notice.unit}`), deadline.notice.amount) : null
  const text =
    deadline.kind === 'trial_end'
      ? t(notice ? 'receipt.deadlineTrialNotice' : 'receipt.deadlineTrial', { notice, day: deadline.day })
      : t(notice ? 'receipt.deadlineRenewalNotice' : 'receipt.deadlineRenewal', { notice })
  const evidenceId = verifiedIds.has(factEvidenceId('cancel_by')) ? factEvidenceId('cancel_by') : null
  // Rounded down to a whole day so the shown date is never later than the backend's safe moment.
  const lastSafeDay = deadline.last_safe_hour != null ? Math.floor(deadline.last_safe_hour / 24) : null
  return (
    <div className="border-s-2 border-fg ps-3" data-testid="receipt-deadline">
      <p className="text-xs font-medium text-muted">{t('receipt.deadline')}</p>
      <p className="mt-0.5 text-sm font-semibold text-fg">{text}</p>
      {lastSafeDay != null ? (
        <p className="mt-1 text-sm font-semibold text-fg" data-testid="deadline-last-safe">
          {t('receipt.lastSafe', { date: formatDate(addDays(today, lastSafeDay), lang), day: lastSafeDay })}
        </p>
      ) : null}
      {deadline.kind === 'trial_end' && deadline.day ? (
        <p className="mt-0.5 text-xs text-muted" data-testid="deadline-trial-end">
          {t('receipt.deadlineDate', { date: formatDate(addDays(today, deadline.day), lang) })}
        </p>
      ) : null}
      <p className="mt-1 text-xs text-muted" data-testid="deadline-note">
        {t(lastSafeDay != null ? 'receipt.lastSafeNote' : deadline.notice ? 'receipt.noDateNote' : 'receipt.noNoticeNote')}
      </p>
      <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
        <SourceButton evidenceId={evidenceId} label={t('receipt.deadline')} onShowEvidence={onShowEvidence} />
        {lastSafeDay != null ? <ProvenanceTag kind="calc" /> : null}
      </div>
    </div>
  )
}

function PathReceipt({ scenario, months, data, verifiedIds, onShowEvidence, today }) {
  const { t, lang } = useLang()
  const money = (v) => formatMoney(v, data.cost.currency, lang)
  const period = data.extracted_terms.billing_period
  const h = scenario.horizons.find((x) => x.months === months)
  const status = scenario.status === 'unavailable' ? 'unavailable' : h?.status || 'unavailable'
  const lineLabel = (ln) => {
    if (ln.kind === 'one_time_fee') return t('receipt.lines.one_time_fee', { label: ln.label || '' })
    if (ln.kind === 'intro_charge') return t('receipt.lines.intro_charge', { n: ln.quantity })
    return t(`receipt.lines.recurring_charge.${period}`, { n: ln.quantity })
  }

  return (
    <section
      aria-labelledby={`path-${scenario.key}`}
      className="flex min-w-0 flex-col rounded-2xl border border-line p-4"
      data-testid={`receipt-${scenario.key}`}
      data-status={status}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 id={`path-${scenario.key}`} className="font-medium text-fg">
          {t(`receipt.${scenario.key}`)}
        </h3>
        <StatusChip status={status} />
      </div>

      {scenario.status === 'unavailable' && scenario.reason ? (
        <p className="mt-3 text-sm text-muted" data-testid={`receipt-unavailable-${scenario.key}`}>
          <span className="block font-medium text-fg">{t('receipt.unavailableTitle')}</span>
          {t(`receipt.unavailable.${scenario.reason}`)}
        </p>
      ) : (
        <>
          {scenario.deadline ? (
            <div className="mt-3">
              <Deadline deadline={scenario.deadline} verifiedIds={verifiedIds} onShowEvidence={onShowEvidence} today={today} />
            </div>
          ) : null}

          {h && h.lines.length ? (
            <ul className="mt-3 divide-y divide-line">
              {h.lines.map((ln, i) => {
                const evidenceId = sourceFieldEvidenceId(ln.source_field)
                return (
                  <li key={i} className="flex items-start justify-between gap-3 py-2" data-testid="receipt-line">
                    <span className="min-w-0">
                      <span dir="auto" className="block text-sm text-fg">
                        {lineLabel(ln)}
                      </span>
                      {ln.quantity > 1 ? (
                        <span className="block text-xs text-muted">
                          <bdi>{t('receipt.lines.each', { amount: money(ln.unit_amount) })}</bdi>
                        </span>
                      ) : null}
                      <SourceButton evidenceId={verifiedIds.has(evidenceId) ? evidenceId : null} label={lineLabel(ln)} onShowEvidence={onShowEvidence} />
                    </span>
                    <bdi className="shrink-0 text-sm font-medium tabular-nums text-fg">{money(ln.amount)}</bdi>
                  </li>
                )
              })}
            </ul>
          ) : h && h.status !== 'unavailable' ? (
            <p className="mt-3 text-sm text-muted">{t('receipt.noLines')}</p>
          ) : null}

          <div className="mt-auto border-t border-dashed border-muted/50 pt-3">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-sm font-medium text-muted">{t('receipt.total', { months: plural(lang, 'month', months) })}</span>
              <bdi className="text-xl font-semibold tabular-nums text-fg" data-testid={`receipt-total-${scenario.key}`}>
                {h && h.total != null && h.status !== 'unavailable' ? money(h.total) : '—'}
              </bdi>
            </div>
            {h && h.status === 'unavailable' && h.missing?.length ? (
              <p className="mt-1 text-xs text-muted">
                {t('cost.missing', { fields: h.missing.map((m) => t(`cost.missingFields.${m}`)).join(lang === 'ar' ? '، ' : ', ') })}
              </p>
            ) : null}
            <div className="mt-2">
              <ProvenanceTag kind="calc" />
            </div>
          </div>

          {scenario.assumption_codes.length ? (
            <ul className="mt-3 space-y-1 text-xs text-muted" data-testid={`receipt-assumptions-${scenario.key}`}>
              {scenario.assumption_codes.map((c) => (
                <li key={c} className="flex gap-1.5">
                  <AlertIcon width={12} height={12} className="mt-0.5 shrink-0 text-unknown-fg" />
                  <span>{assumptionText(t, lang, c)}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </section>
  )
}

export default function FutureReceipt({ data, onShowEvidence, today = new Date() }) {
  const { t, lang } = useLang()
  const [months, setMonths] = useState(12)
  const { cost, decision } = data
  const money = (v) => formatMoney(v, cost.currency, lang)
  const verifiedIds = useMemo(() => new Set(collectEvidence(data).verified.map((it) => it.id)), [data])
  const diff = decision.difference.find((d) => d.months === months)
  // A positive amount means a charge whose timing FAIR has not verified. A free trial with no fee owes nothing.
  const timingAssumed = Number(cost.due_at_signup) > 0
  const withheld = cost.withheld || []
  const notCounted = cost.not_counted || []
  const statedPrice = data.extracted_terms.recurring_price
  const noteTexts = cost.note_codes ? cost.note_codes.map((c) => t(`cost.noteText.${c}`)) : cost.notes || []

  let next
  if (cost.first_paid_charge_day != null && cost.first_paid_charge_amount != null) {
    const amount = money(cost.first_paid_charge_amount)
    next =
      cost.first_paid_charge_day > 0 ? (
        <>
          <bdi>{t('cost.firstChargeOn', { amount, day: cost.first_paid_charge_day })}</bdi>
          <span className="block text-xs font-normal text-muted">
            {t('cost.firstChargeDate', { date: formatDate(addDays(today, cost.first_paid_charge_day), lang) })}
          </span>
        </>
      ) : (
        <bdi>{t('cost.firstChargeImmediate', { amount })}</bdi>
      )
  } else {
    // Withheld is not "no charge": the terms state charges that FAIR cannot total.
    next = <span className="font-medium text-muted">{t(withheld.length ? 'cost.unknownValue' : 'cost.firstChargeNone')}</span>
  }

  return (
    <Chapter id="receipt-heading" title={t('receipt.title')} testId="future-receipt">

      {withheld.length ? (
        <div className="mb-6 border-s-2 border-unknown-solid ps-4 text-sm text-fg" data-testid="projection-withheld">
          <p className="font-medium text-fg">{t('receipt.withheld.title')}</p>
          <ul className="mt-2 space-y-2">
            {withheld.map((w) => (
              <li key={`${w.code}-${w.amount}-${w.rate}`} className="min-w-0">
                <span className="block">{t(`receipt.withheld.${w.code}`, { amount: w.amount != null ? money(w.amount) : '', rate: w.rate ?? '' })}</span>
                <span dir="auto" className="block break-words text-xs text-muted">
                  {quote(w.quote, lang)}
                </span>
              </li>
            ))}
          </ul>
          {statedPrice != null ? (
            <p className="mt-2 text-xs font-medium" data-testid="stated-price">
              <bdi>{t('receipt.withheld.statedPrice', { amount: money(statedPrice) })}</bdi>
            </p>
          ) : null}
          <div className="mt-2">
            <ProvenanceTag kind="unknown" />
          </div>
        </div>
      ) : null}

      <dl className="grid gap-5 sm:grid-cols-2 sm:gap-8">
        <div className="min-w-0">
          <dt className="text-xs text-muted">{t(timingAssumed ? 'cost.dueExpected' : 'cost.dueAtSignup')}</dt>
          <dd className="mt-0.5 font-medium text-fg" data-testid="due-now">
            {cost.due_at_signup != null ? <bdi>{money(cost.due_at_signup)}</bdi> : <span className="font-medium text-muted">{t('cost.unknownValue')}</span>}
          </dd>
          {timingAssumed ? (
            <dd className="mt-1.5 space-y-1 text-xs text-muted" data-testid="due-timing-note">
              <span className="block">{t('cost.dueTimingNote')}</span>
              <ProvenanceTag kind="assumption" />
            </dd>
          ) : null}
        </div>
        <div className="min-w-0">
          <dt className="text-xs text-muted">{t('cost.firstCharge')}</dt>
          <dd className="mt-0.5 font-medium text-fg" data-testid="next-charge">
            {next}
          </dd>
        </div>
      </dl>

      <div className="mt-6 flex flex-wrap items-center gap-x-4 gap-y-1">
        <span className="sr-only" id="horizon-label">
          {t('receipt.horizon')}
        </span>
        <div role="group" aria-labelledby="horizon-label" className="inline-flex gap-5 border-b border-line" data-testid="horizon-switch">
          {HORIZONS.map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={months === m}
              onClick={() => setMonths(m)}
              className={`-mb-px min-h-[40px] border-b-2 text-sm font-medium transition-colors ${
                months === m ? 'border-fg text-fg' : 'border-transparent text-muted hover:text-fg'
              }`}
            >
              {plural(lang, 'month', m)}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <PathReceipt scenario={decision.continue_path} months={months} data={data} verifiedIds={verifiedIds} onShowEvidence={onShowEvidence} today={today} />
        <PathReceipt scenario={decision.cancel_path} months={months} data={data} verifiedIds={verifiedIds} onShowEvidence={onShowEvidence} today={today} />
      </div>

      {notCounted.length ? (
        <div className="mt-5 border-s-2 border-unknown-solid ps-4 text-sm" data-testid="amounts-not-counted">
          <p className="font-medium text-fg">{t('receipt.notCounted')}</p>
          <ul className="mt-2 space-y-2">
            {notCounted.map((n) => (
              <li key={`${n.amount}-${n.rate}`} className="min-w-0 text-fg">
                <bdi className="font-semibold">{n.amount != null ? money(n.amount) : t('receipt.notCountedRate', { rate: n.rate })}</bdi>
                <span dir="auto" className="block break-words text-xs text-muted">
                  {quote(n.quote, lang)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {diff ? (
        <div className="mt-5" data-testid="receipt-difference">
          <p className="font-semibold text-fg">
            <bdi>{t('receipt.difference', { amount: money(diff.amount) })}</bdi>
          </p>
          <p className="mt-0.5 text-xs text-muted">{t('receipt.differenceNote')}</p>
          <div className="mt-2">
            <ProvenanceTag kind="calc" />
          </div>
        </div>
      ) : null}

      {noteTexts.length ? (
        <ul className="mt-4 list-disc space-y-1 ps-5 text-xs text-muted">
          {noteTexts.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      ) : null}
    </Chapter>
  )
}

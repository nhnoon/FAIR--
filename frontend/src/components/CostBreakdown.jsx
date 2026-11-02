import { useLang } from '../i18n/LanguageContext.jsx'
import { addDays, formatDate, formatMoney, plural } from '../lib/format.js'
import { AlertIcon, CalculatorIcon, CheckIcon, MinusIcon } from './icons.jsx'

// Status is shown by icon + text + colour, never colour alone.
const STATUS = {
  complete: { cls: 'bg-subtle text-fg ring-line', Icon: CheckIcon },
  conditional: { cls: 'bg-unknown-bg text-unknown-fg ring-unknown-line', Icon: AlertIcon },
  unavailable: { cls: 'bg-subtle text-muted ring-line', Icon: MinusIcon },
}

function Stat({ label, children }) {
  return (
    <div className="min-w-0 rounded-xl border border-line bg-subtle p-4">
      <dt className="text-xs font-medium text-muted">{label}</dt>
      <dd className="mt-1 break-words text-base font-semibold text-fg">{children}</dd>
    </div>
  )
}

export default function CostBreakdown({ cost, today = new Date() }) {
  const { t, lang } = useLang()
  const money = (v) => formatMoney(v, cost.currency, lang)
  const unknown = <span className="font-medium text-muted">{t('cost.unknownValue')}</span>

  let firstCharge
  if (cost.first_paid_charge_day != null && cost.first_paid_charge_amount != null) {
    const amount = money(cost.first_paid_charge_amount)
    firstCharge =
      cost.first_paid_charge_day > 0 ? (
        <>
          <bdi>{t('cost.firstChargeOn', { amount, day: cost.first_paid_charge_day })}</bdi>
          <span className="mt-0.5 block text-xs font-normal text-muted">
            {t('cost.firstChargeDate', { date: formatDate(addDays(today, cost.first_paid_charge_day), lang) })}
          </span>
        </>
      ) : (
        <bdi>{t('cost.firstChargeImmediate', { amount })}</bdi>
      )
  } else {
    // Withheld is not "no charge".
    firstCharge = <span className="font-medium text-muted">{t(cost.withheld?.length ? 'cost.unknownValue' : 'cost.firstChargeNone')}</span>
  }

  // Assumption codes, de-duplicated across the three projections, in first-seen order.
  const codes = []
  cost.projections.forEach((p) => (p.assumption_codes || []).forEach((c) => codes.includes(c) || codes.push(c)))
  const assumptionTexts = codes.map((c) => t(`cost.assumptionText.${c}`))
  // Fallback for a backend without codes: show its English texts rather than nothing.
  if (codes.length === 0) cost.projections.forEach((p) => p.assumptions.forEach((a) => assumptionTexts.includes(a) || assumptionTexts.push(a)))

  const noteTexts = cost.note_codes ? cost.note_codes.map((c) => t(`cost.noteText.${c}`)) : cost.notes || []
  const feesTotal = Number(cost.one_time_fees_total) > 0 ? money(cost.one_time_fees_total) : null
  const uncertain = cost.projections.some((p) => p.status !== 'complete')

  return (
    <section aria-labelledby="cost-heading" className="card p-5 sm:p-6">
      <h2 id="cost-heading" className="section-title flex items-center gap-2">
        <span className="grid h-6 w-6 place-items-center rounded-md bg-primary text-primary-fg">
          <CalculatorIcon width={14} height={14} />
        </span>
        {t('cost.heading')}
      </h2>
      <p className="mt-1 text-sm text-muted">{t('cost.subtitle')}</p>

      <dl className={`mt-5 grid gap-3 ${feesTotal ? 'sm:grid-cols-3' : 'sm:grid-cols-2'}`}>
        <Stat label={t(Number(cost.due_at_signup) > 0 ? 'cost.dueExpected' : 'cost.dueAtSignup')}>
          {cost.due_at_signup != null ? <bdi>{money(cost.due_at_signup)}</bdi> : unknown}
          {Number(cost.due_at_signup) > 0 ? (
            <span className="mt-0.5 block text-xs font-normal text-muted" data-testid="due-timing-note">
              {t('cost.dueTimingNote')}
            </span>
          ) : null}
        </Stat>
        <Stat label={t('cost.firstCharge')}>{firstCharge}</Stat>
        {feesTotal ? (
          <Stat label={t('cost.feesTotal')}>
            <bdi>{feesTotal}</bdi>
          </Stat>
        ) : null}
      </dl>

      <h4 className="mt-6 text-sm font-semibold text-fg">{t('cost.projectionsLabel')}</h4>
      <ul className="mt-2 grid gap-3 sm:grid-cols-3" aria-label={t('cost.projectionsLabel')}>
        {cost.projections.map((p) => {
          const s = STATUS[p.status]
          return (
            <li
              key={p.months}
              data-testid={`projection-${p.months}`}
              className="flex min-w-0 flex-col rounded-xl border border-line bg-surface p-4"
            >
              <span className="text-sm font-medium text-muted">{plural(lang, 'month', p.months)}</span>
              <span className="mt-1 break-words text-2xl font-bold tabular-nums text-fg">
                {p.status !== 'unavailable' && p.total != null ? <bdi>{money(p.total)}</bdi> : '—'}
              </span>
              <span className={`chip mt-3 w-fit ${s.cls}`}>
                <s.Icon width={12} height={12} />
                {t(`cost.status.${p.status}`)}
              </span>
              {p.status === 'unavailable' && p.missing?.length ? (
                <span className="mt-2 text-xs text-muted">
                  {t('cost.missing', {
                    fields: p.missing.map((m) => t(`cost.missingFields.${m}`)).join(lang === 'ar' ? '، ' : ', '),
                  })}
                </span>
              ) : null}
            </li>
          )
        })}
      </ul>

      {assumptionTexts.length || noteTexts.length ? (
        <div
          className={`mt-5 rounded-xl border p-4 ${uncertain ? 'border-unknown-line bg-unknown-bg' : 'border-line bg-subtle'}`}
          data-testid="assumptions"
        >
          {assumptionTexts.length ? (
            <>
              <h4 className={`flex items-center gap-2 text-sm font-semibold ${uncertain ? 'text-unknown-fg' : 'text-fg'}`}>
                {uncertain ? <AlertIcon width={16} height={16} /> : null}
                {uncertain ? t('cost.assumptionsUncertain') : t('cost.assumptions')}
              </h4>
              <ul className="mt-2 list-disc space-y-1 ps-5 text-sm text-muted">
                {assumptionTexts.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </>
          ) : null}
          {noteTexts.length ? (
            <>
              <h4 className="mt-3 text-sm font-semibold text-fg">{t('cost.notes')}</h4>
              <ul className="mt-2 list-disc space-y-1 ps-5 text-sm text-muted">
                {noteTexts.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

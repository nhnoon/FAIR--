import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import withheldCases from './fixtures/financial_withheld.json'
import replay from './fixtures/phase11_replay.json'
import { HEALTH, analyzeCalls, fakeResponse, liveResponse, mockFetch, mockFetchWith, renderApp } from './helpers.jsx'

const ANALYZE = 'Reveal the Gap'
const horizon = (name) => within(screen.getByTestId('horizon-switch')).getByRole('button', { name })
const nav = (name) => within(screen.getByTestId('sidebar')).getByRole('button', { name: new RegExp(`^${name}`) })

// Users paste offer terms; pasting also keeps tests fast.
async function fillAndSubmit(user, terms, expectation) {
  await user.click(screen.getByLabelText('Subscription terms'))
  await user.paste(terms)
  await user.click(screen.getByLabelText('Your expectation'))
  await user.paste(expectation)
  await user.click(screen.getByRole('button', { name: ANALYZE }))
}

async function analyzeLive(user, id = 'trial-autorenew') {
  const live = liveResponse(id)
  const fetchMock = mockFetch(fakeResponse(200, live.body))
  renderApp()
  await fillAndSubmit(user, live.terms, live.expectation)
  await screen.findByTestId('live-badge')
  return { live, fetchMock }
}

// Offline replay of real Phase 11 model outputs through today's backend. Not live results.
describe('Future Receipt from replayed model outputs', () => {
  async function show(user, id, lang = 'en') {
    const { terms, expectation, body } = replay.cases[id]
    mockFetch(fakeResponse(200, body))
    renderApp(lang)
    const [termsLabel, expectationLabel, button] = lang === 'en' ? ['Subscription terms', 'Your expectation', ANALYZE] : ['شروط الاشتراك', 'توقعك', 'اكشف الفجوة']
    await user.click(screen.getByLabelText(termsLabel))
    await user.paste(terms)
    await user.click(screen.getByLabelText(expectationLabel))
    await user.paste(expectation)
    await user.click(screen.getByRole('button', { name: button }))
    await screen.findByTestId('live-badge')
  }

  it('FAIR-003: recurring totals and a conditional difference', async () => {
    const user = userEvent.setup()
    await show(user, 'FAIR-003')
    for (const [label, keep, diff] of [['1 month', '9.99 USD', '0.00 USD'], ['3 months', '29.97 USD', '19.98 USD'], ['12 months', '119.88 USD', '109.89 USD']]) {
      await user.click(horizon(label))
      expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent(keep)
      expect(screen.getByTestId('receipt-total-cancel')).toHaveTextContent('9.99 USD')
      expect(screen.getByTestId('receipt-difference')).toHaveTextContent(diff)
    }
    expect(screen.getByTestId('receipt-continue')).toHaveAttribute('data-status', 'complete')
    expect(screen.getByTestId('receipt-cancel')).toHaveAttribute('data-status', 'conditional')
    expect(screen.getByTestId('receipt-difference')).toHaveTextContent('A calculation, not a promise')
    expect(screen.getByTestId('receipt-deadline')).toHaveTextContent('At least 48 hours before the first renewal')
    expect(screen.queryByTestId('deadline-last-safe')).not.toBeInTheDocument()
  })

  it('FAIR-007: introductory then recurring lines, labelled assumption, and no invented cancel path', async () => {
    const user = userEvent.setup()
    await show(user, 'FAIR-007')
    const keep = screen.getByTestId('receipt-continue')
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('172.39 USD')
    expect(keep).toHaveAttribute('data-status', 'conditional')
    expect(keep).toHaveTextContent('7.50 USD')
    expect(keep).toHaveTextContent('164.89 USD')
    expect(keep).toHaveTextContent('The introductory price is assumed to last one billing period')
    expect(screen.getByTestId('receipt-unavailable-cancel')).toBeInTheDocument()
    expect(screen.queryByTestId('receipt-difference')).not.toBeInTheDocument()
  })

  it.each([
    ['en', 'billing_period_mismatch', 'The billing period differs from the one stated with this price'],
    ['ar', 'billing_period_mismatch', 'دورة الفوترة تختلف عن الدورة المذكورة مع هذا السعر'],
    ['en', 'billing_period_unsupported', 'FAIR cannot calculate this billing period'],
    ['ar', 'one_time_not_recurring', 'يذكر الاقتباس رسمًا لمرة واحدة وليس سعرًا متكررًا'],
  ])('explains an excluded price (%s, %s)', async (lang, reason, text) => {
    const user = userEvent.setup()
    const original = replay.cases['FAIR-005'].body
    replay.cases['FAIR-005'].body = {
      ...original,
      rejected_facts: [{ field: 'recurring_price', value: '120', evidence: { quote: 'Annual plan: USD 120/year.', verified: false, reason } }],
    }
    try {
      await show(user, 'FAIR-005', lang)
    } finally {
      replay.cases['FAIR-005'].body = original
    }
    expect(screen.getByTestId('uncertain')).toHaveTextContent(text)
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('—')
  })

  it.each([
    ['en', 'The terms show a dollar sign without naming the country'],
    ['ar', 'تعرض الشروط علامة الدولار دون تحديد البلد'],
  ])('states the dollar-sign assumption (%s)', async (lang, text) => {
    const user = userEvent.setup()
    const original = replay.cases['FAIR-003'].body
    replay.cases['FAIR-003'].body = {
      ...original,
      cost: { ...original.cost, currency: '$', note_codes: [...original.cost.note_codes, 'currency_symbol_ambiguous'] },
    }
    try {
      await show(user, 'FAIR-003', lang)
    } finally {
      replay.cases['FAIR-003'].body = original
    }
    expect(screen.getByTestId('future-receipt')).toHaveTextContent(text)
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('119.88 $')
  })

  it.each([
    ['en', 'FAIR-003', 'The terms give this notice period but no date', 'found no notice period'],
    ['ar', 'FAIR-023', 'تذكر الشروط مهلة الإشعار هذه دون تاريخ', 'لم يجد FAIR مهلة إشعار'],
  ])('a renewal deadline with a stated notice never says no notice was found (%s)', async (lang, id, right, wrong) => {
    const user = userEvent.setup()
    replay.cases[id] ||= { ...liveResponse('decision-twin'), body: { ...liveResponse('decision-twin').body, decision: { ...replay.cases['FAIR-003'].body.decision } } }
    await show(user, id, lang)
    expect(screen.getByTestId('deadline-note')).toHaveTextContent(right)
    expect(screen.getByTestId('receipt-deadline')).not.toHaveTextContent(wrong)
    expect(screen.queryByTestId('deadline-last-safe')).not.toBeInTheDocument()
  })

  it('does not say a price is absent from terms that may state it', async () => {
    const user = userEvent.setup()
    await show(user, 'FAIR-005')
    const missing = screen.getByTestId('not-stated')
    expect(missing).toHaveTextContent('FAIR could not confirm these from the terms: Price')
    expect(missing).not.toHaveTextContent('Not stated in the terms')
  })

  it('FAIR-005: no price means no projection', async () => {
    const user = userEvent.setup()
    await show(user, 'FAIR-005')
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('—')
    expect(screen.getByTestId('receipt-continue')).toHaveAttribute('data-status', 'unavailable')
    expect(screen.queryByTestId('receipt-difference')).not.toBeInTheDocument()
  })

  it('shows the same grounded amounts in Arabic', async () => {
    const user = userEvent.setup()
    await show(user, 'FAIR-003', 'ar')
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('119.88 USD')
    expect(screen.getByTestId('receipt-difference')).toHaveTextContent('109.89 USD')
    expect(screen.getByTestId('receipt-difference')).toHaveTextContent('هذا حساب وليس وعدًا')
    expect(screen.getByTestId('receipt-deadline')).toHaveTextContent('قبل أول تجديد')
  })

  it('shows introductory and recurring amounts in Arabic', async () => {
    const user = userEvent.setup()
    await show(user, 'FAIR-007', 'ar')
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('172.39 USD')
    expect(screen.getByTestId('receipt-continue')).toHaveTextContent('7.50 USD')
    expect(screen.getByTestId('receipt-unavailable-cancel')).toBeInTheDocument()
  })
})

describe('Decision reveal: belief beside the cost of each choice', () => {
  async function showBody(user, { terms, expectation, body }, lang = 'en') {
    mockFetch(fakeResponse(200, body))
    renderApp(lang)
    const [termsLabel, expectationLabel, button] = lang === 'en' ? ['Subscription terms', 'Your expectation', ANALYZE] : ['شروط الاشتراك', 'توقعك', 'اكشف الفجوة']
    await user.click(screen.getByLabelText(termsLabel))
    await user.paste(terms)
    await user.click(screen.getByLabelText(expectationLabel))
    await user.paste(expectation)
    await user.click(screen.getByRole('button', { name: button }))
    await screen.findByTestId('live-badge')
  }

  it('puts the contradicted belief beside the verified sentence and three backend-priced choices', async () => {
    const user = userEvent.setup()
    await showBody(user, liveResponse('decision-twin'))
    expect(screen.getByTestId('reveal-belief')).toHaveTextContent('The subscription ends automatically.')
    expect(screen.getByTestId('reveal-terms')).toHaveTextContent('renews automatically at USD 9.99 per month')
    expect(screen.getByTestId('reveal-amount-keep')).toHaveTextContent('119.88 USD')
    expect(screen.getByTestId('reveal-amount-cancel')).toHaveTextContent('0.00 USD')
    expect(screen.getByTestId('reveal-amount-miss')).toHaveTextContent('At least 9.99 USD')
    expect(screen.getByTestId('reveal-choice-keep')).toHaveAttribute('aria-pressed', 'true')
  })

  it('shows amounts exactly as the backend sent them: nothing is calculated in the browser', async () => {
    const user = userEvent.setup()
    const live = liveResponse('decision-twin')
    const decision = structuredClone(live.body.decision)
    decision.continue_path.horizons.find((h) => h.months === 12).total = '123.45'
    decision.continue_path.horizons.find((h) => h.months === 1).total = '77.70'
    decision.cancel_path.horizons.find((h) => h.months === 12).total = '5.55'
    await showBody(user, { ...live, body: { ...live.body, decision } })
    expect(screen.getByTestId('reveal-amount-keep')).toHaveTextContent('123.45 USD')
    expect(screen.getByTestId('reveal-amount-cancel')).toHaveTextContent('5.55 USD')
    expect(screen.getByTestId('reveal-amount-miss')).toHaveTextContent('77.70 USD')
  })

  it('separates verified, assumed and unknown for each choice, and never promises an outcome', async () => {
    const user = userEvent.setup()
    await showBody(user, liveResponse('decision-twin'))
    const reveal = screen.getByTestId('decision-reveal')
    expect(screen.getByTestId('reveal-verified')).toHaveTextContent('USD 9.99 per month')
    expect(screen.getByTestId('reveal-assumed')).toHaveTextContent('Assumes you do not cancel during this period.')
    expect(screen.getByTestId('reveal-unknown')).toHaveTextContent('I can cancel whenever I want.')

    await user.click(screen.getByTestId('reveal-choice-cancel'))
    expect(screen.getByTestId('reveal-choice-cancel')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('reveal-verified')).toHaveTextContent('cancel at least 48 hours before the trial ends')
    expect(screen.getByTestId('reveal-assumed')).toHaveTextContent('FAIR cannot confirm that cancelling is free.')
    expect(screen.getByTestId('reveal-assumed')).toHaveTextContent('No refund is assumed.')

    await user.click(screen.getByTestId('reveal-choice-miss'))
    expect(screen.getByTestId('reveal-assumed')).toHaveTextContent('no refund is given')
    expect(screen.getByTestId('reveal-unknown')).toHaveTextContent('Whether cancelling after the deadline stops later charges')
    expect(reveal).not.toHaveTextContent(/saving|you will save|guarantee|you can cancel/i)
  })

  it('lists a passage once when one verified quote sits inside another', async () => {
    const user = userEvent.setup()
    const live = liveResponse('decision-twin')
    const long = 'When the trial ends, your subscription renews automatically at USD 9.99 per month until you cancel.'
    const facts = live.body.facts.map((f) => (f.field === 'recurring_price' ? { ...f, evidence: { ...f.evidence, quote: long } } : f.field === 'cancel_by' ? { ...f, evidence: { ...f.evidence, quote: 'renews automatically' } } : f))
    await showBody(user, { ...live, body: { ...live.body, facts } })
    await user.click(screen.getByTestId('reveal-choice-miss'))
    expect(within(screen.getByTestId('reveal-verified')).getAllByRole('listitem')).toHaveLength(1)
  })

  it('a verified source link opens the quote in the source text', async () => {
    const user = userEvent.setup()
    await showBody(user, liveResponse('decision-twin'))
    await user.click(within(screen.getByTestId('reveal-verified')).getAllByRole('button')[0])
    const active = screen.getByTestId('source-text').querySelectorAll('mark[data-active="true"]')
    expect([...active].map((m) => m.textContent).join('')).toContain('USD 9.99 per month')
  })

  it('offers no missed-deadline figure when the deadline is a renewal, because no such total exists', async () => {
    const user = userEvent.setup()
    await showBody(user, replay.cases['FAIR-003'])
    expect(screen.getByTestId('reveal-amount-keep')).toHaveTextContent('119.88 USD')
    expect(screen.getByTestId('reveal-amount-cancel')).toHaveTextContent('9.99 USD')
    expect(screen.queryByTestId('reveal-choice-miss')).not.toBeInTheDocument()
  })

  it.each([
    ['no contradiction', (b) => ({ ...b, claims: b.claims.map((c) => ({ ...c, verdict: 'UNKNOWN' })) })],
    ['a downgraded contradiction', (b) => ({ ...b, claims: b.claims.map((c) => (c.verdict === 'CONTRADICTION' ? { ...c, downgraded: true } : c)) })],
    ['an unverified quote', (b) => ({ ...b, claims: b.claims.map((c) => (c.verdict === 'CONTRADICTION' ? { ...c, evidence: { ...c.evidence, verified: false } } : c)) })],
    ['an unavailable cancel path', (b) => ({ ...b, decision: { ...b.decision, cancel_path: { key: 'cancel', status: 'unavailable', reason: 'renewal_not_stated', horizons: [], assumption_codes: [] } } })],
    ['an unavailable keep path and cancel path', (b) => ({ ...b, decision: { ...b.decision, difference: [], continue_path: { ...b.decision.continue_path, status: 'unavailable', horizons: b.decision.continue_path.horizons.map((h) => ({ ...h, status: 'unavailable', total: null })) }, cancel_path: { key: 'cancel', status: 'unavailable', reason: 'renewal_not_stated', horizons: [], assumption_codes: [] } } })],
  ])('is withheld with %s', async (_name, change) => {
    const user = userEvent.setup()
    const live = liveResponse('decision-twin')
    await showBody(user, { ...live, body: change(live.body) })
    expect(screen.queryByTestId('decision-reveal')).not.toBeInTheDocument()
  })

  it.each(['FAIR-005', 'FAIR-007'])('is withheld on %s, which has no verified contradiction', async (id) => {
    const user = userEvent.setup()
    await showBody(user, replay.cases[id])
    expect(screen.queryByTestId('decision-reveal')).not.toBeInTheDocument()
  })

  it('works in Arabic with the same backend amounts', async () => {
    const user = userEvent.setup()
    await showBody(user, liveResponse('decision-twin'), 'ar')
    const reveal = screen.getByRole('region', { name: 'توقعك، وتكلفة كل خيار' })
    expect(reveal).toHaveTextContent('كنت تعتقد')
    expect(screen.getByTestId('reveal-amount-keep')).toHaveTextContent('119.88 USD')
    expect(screen.getByTestId('reveal-amount-miss')).toHaveTextContent('9.99 USD على الأقل')
    await user.click(screen.getByTestId('reveal-choice-miss'))
    expect(screen.getByTestId('reveal-unknown')).toHaveTextContent('هل يوقف الإلغاء بعد الموعد')
    expect(reveal.textContent).not.toMatch(/reveal\.|cost\.status|undefined/)
  })
})

describe('totals are withheld when the verified prices would not be complete', () => {
  async function run(user, { terms, expectation, body }, lang = 'en') {
    mockFetch(fakeResponse(200, body))
    renderApp(lang)
    const [termsLabel, expectationLabel, button] = lang === 'en' ? ['Subscription terms', 'Your expectation', ANALYZE] : ['شروط الاشتراك', 'توقعك', 'اكشف الفجوة']
    await user.click(screen.getByLabelText(termsLabel))
    await user.paste(terms)
    await user.click(screen.getByLabelText(expectationLabel))
    await user.paste(expectation)
    await user.click(screen.getByRole('button', { name: button }))
    await screen.findByTestId('live-badge')
  }

  it.each([
    ['CH-04', 'This price of 20.00 USD is per seat, user or device', 'Stated price, not a total: 20.00 USD'],
    ['CH-05', 'The terms also state 4.50 USD, which FAIR could not include', 'Stated price, not a total: 10.00 USD'],
    ['CH-11', 'The terms both state and deny automatic renewal', 'Stated price, not a total: 19.00 SAR'],
  ])('%s shows why, keeps the stated price, and shows no total or zero', async (id, reason, stated) => {
    const user = userEvent.setup()
    await run(user, withheldCases.cases[id])
    expect(screen.getByTestId('projection-withheld')).toHaveTextContent(reason)
    expect(screen.getByTestId('stated-price')).toHaveTextContent(stated)
    expect(screen.queryByTestId('receipt-total-continue')).not.toBeInTheDocument() // the reason replaces the total row
    expect(screen.getByTestId('receipt-unavailable-continue')).toBeInTheDocument()
    expect(screen.getByTestId('receipt-continue')).toHaveAttribute('data-status', 'unavailable')
    expect(screen.getByTestId('receipt-cancel')).toHaveAttribute('data-status', 'unavailable')
    expect(screen.getByTestId('due-now')).toHaveTextContent('Cannot be determined')
    expect(screen.getByTestId('due-now')).not.toHaveTextContent('0.00')
    expect(screen.getByTestId('next-charge')).not.toHaveTextContent('No automatic charge')
    expect(screen.queryByTestId('receipt-difference')).not.toBeInTheDocument()
  })

  describe('percentage charges and tax', () => {
    const { vat_en: vatEn, vat_ar: vatAr, tax_ar: taxAr, fee_en: feeEn, fee_ar: feeAr, trial_fee_en: trialFee } = withheldCases.percent_cases

    it('withholds a VAT-exclusive total, names the rate and calculates nothing', async () => {
      const user = userEvent.setup()
      await run(user, vatEn)
      expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'CONTRADICTION')
      expect(screen.queryByTestId('decision-reveal')).not.toBeInTheDocument()
      const box = screen.getByTestId('projection-withheld')
      expect(box).toHaveTextContent('a charge of 15%')
      expect(box).toHaveTextContent('plus 15% VAT')
      expect(screen.getByTestId('stated-price')).toHaveTextContent('Stated price, not a total: 10.00 USD')
      expect(screen.getByTestId('due-now')).toHaveTextContent('Cannot be determined')
      expect(screen.getByTestId('next-charge')).toHaveTextContent('Cannot be determined')
      expect(screen.getByTestId('receipt-unavailable-continue')).toHaveTextContent('percentage charge')
      expect(document.body).not.toHaveTextContent(/(^|[^0-9])0.00 USD|120\.00 USD|138\.00 USD|11\.50 USD/)
    })

    it('explains the same result in Arabic', async () => {
      const user = userEvent.setup()
      await run(user, vatAr, 'ar')
      expect(screen.getByTestId('projection-withheld')).toHaveTextContent('15٪')
      expect(screen.getByTestId('due-now')).toHaveTextContent('لا يمكن تحديده')
      expect(screen.getByTestId('next-charge')).toHaveTextContent('لا يمكن تحديده')
      expect(screen.queryByTestId('decision-reveal')).not.toBeInTheDocument()
      expect(document.body).not.toHaveTextContent(/(^|[^0-9])0.00 SAR|120\.00 SAR/)
      expect(document.body.textContent).not.toMatch(/receipt\.withheld|cost\.missingFields|receipt\.unavailable/)
    })

    it('says tax with no rate is not estimated, in Arabic', async () => {
      const user = userEvent.setup()
      await run(user, taxAr, 'ar')
      expect(screen.getByTestId('projection-withheld')).toHaveTextContent('لا يقدّر FAIR الضريبة')
      expect(screen.getByTestId('receipt-unavailable-continue')).toHaveTextContent('تذكر الشروط ضريبة')
      expect(document.body.textContent).not.toMatch(/receipt\.withheld|receipt\.unavailable/)
    })

    it('does not show a fee as a first payment when its tax is excluded', async () => {
      const user = userEvent.setup()
      await run(user, trialFee)
      expect(screen.getByTestId('due-now')).toHaveTextContent('Cannot be determined')
      expect(screen.getByTestId('due-now')).not.toHaveTextContent('5.00')
    })

    it('labels a conditional percentage fee and shares one total across Reveal and Receipt', async () => {
      const user = userEvent.setup()
      await run(user, feeEn)
      expect(screen.getByTestId('amounts-not-counted')).toHaveTextContent('3%, not calculated')
      expect(screen.getByTestId('amounts-not-counted')).toHaveTextContent('if you pay by card')
      expect(screen.getByTestId('reveal-amount-keep')).toHaveTextContent('120.00 USD')
      expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('120.00 USD')
      expect(screen.getByTestId('reveal-amount-miss')).toHaveTextContent('At least 10.00 USD')
      expect(screen.getByTestId('reveal-assumed')).toHaveTextContent('amount or percentage that this figure does not count')
      await user.click(screen.getByTestId('reveal-choice-miss'))
      expect(screen.getByTestId('reveal-assumed')).toHaveTextContent('amount or percentage that this figure does not count')
    })

    it('labels it in Arabic too', async () => {
      const user = userEvent.setup()
      await run(user, feeAr, 'ar')
      expect(screen.getByTestId('amounts-not-counted')).toHaveTextContent('3٪، لم تُحسب')
      expect(screen.getByTestId('reveal-amount-keep')).toHaveTextContent('120.00 SAR')
      expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('120.00 SAR')
    })
  })

  it('Decision Reveal shows no amounts when the receipt withholds them, even with a verified contradiction', async () => {
    const user = userEvent.setup()
    await run(user, withheldCases.cases['CH-05'])
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'CONTRADICTION')
    expect(screen.queryByTestId('decision-reveal')).not.toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('120.00 USD')
  })

  it('names what is missing in Arabic', async () => {
    const user = userEvent.setup()
    await run(user, withheldCases.cases['CH-04'], 'ar')
    expect(screen.getByTestId('projection-withheld')).toHaveTextContent('لا يعرض FAIR إجماليًا')
    expect(screen.getByTestId('projection-withheld')).toHaveTextContent('لكل مقعد أو مستخدم أو جهاز')
    expect(screen.getByTestId('stated-price')).toHaveTextContent('السعر المذكور، وليس إجماليًا')
    expect(screen.getByTestId('receipt-unavailable-continue')).toHaveTextContent('يعتمد السعر على كمية لا تذكرها الشروط')
    expect(screen.getByTestId('receipt-unavailable-cancel')).toHaveTextContent('يعتمد السعر على كمية لا تذكرها الشروط')
    expect(document.body.textContent).not.toMatch(/receipt\.withheld|cost\.missingFields/)
  })

  it.each([
    ['en', 'Optional or conditional amounts this total does not count', 'The terms state an optional or conditional amount'],
    ['ar', 'مبالغ اختيارية أو مشروطة لا يحسبها هذا الإجمالي', 'تذكر الشروط مبلغًا أو نسبة اختيارية أو مشروطة'],
  ])('labels and names an amount left out of a shown total (%s)', async (lang, heading, assumption) => {
    const user = userEvent.setup()
    const live = replay.cases['FAIR-003']
    const body = structuredClone(live.body)
    body.cost.not_counted = [{ amount: '5.00', quote: 'A late fee of USD 5 applies if a payment fails.' }]
    body.decision.continue_path.status = 'conditional'
    body.decision.continue_path.assumption_codes.push('amount_not_counted')
    body.decision.continue_path.horizons.forEach((h) => { h.status = 'conditional' })
    await run(user, { ...live, body }, lang)
    expect(screen.getByTestId('amounts-not-counted')).toHaveTextContent(heading)
    expect(screen.getByTestId('amounts-not-counted')).toHaveTextContent('5.00 USD')
    expect(screen.getByTestId('receipt-continue')).toHaveAttribute('data-status', 'conditional')
    expect(screen.getByTestId('receipt-continue')).toHaveTextContent(assumption)
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('119.88 USD')
  })

  it('the older cost card names what is missing, in both languages', async () => {
    const user = userEvent.setup()
    const { decision, claims, claims_summary, ...legacy } = withheldCases.cases['CH-04'].body
    await run(user, { ...withheldCases.cases['CH-04'], body: legacy })
    expect(screen.getByTestId('projection-12')).toHaveTextContent('how many seats or users')
    expect(screen.getByTestId('projection-12')).not.toHaveTextContent('240')
  })

  it('an older response without these fields still renders normally', async () => {
    const user = userEvent.setup()
    const live = replay.cases['FAIR-003']
    const body = structuredClone(live.body)
    delete body.cost.withheld
    delete body.cost.not_counted
    await run(user, { ...live, body })
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('119.88 USD')
    expect(screen.queryByTestId('projection-withheld')).not.toBeInTheDocument()
  })
})

describe('payment timing is not presented as verified', () => {
  async function run(user, { terms, expectation, body }, lang = 'en') {
    mockFetch(fakeResponse(200, body))
    renderApp(lang)
    const [termsLabel, expectationLabel, button] = lang === 'en' ? ['Subscription terms', 'Your expectation', ANALYZE] : ['شروط الاشتراك', 'توقعك', 'اكشف الفجوة']
    await user.click(screen.getByLabelText(termsLabel))
    await user.paste(terms)
    await user.click(screen.getByLabelText(expectationLabel))
    await user.paste(expectation)
    await user.click(screen.getByRole('button', { name: button }))
    await screen.findByTestId('live-badge')
  }

  it('labels an amount with no stated charge time as an assumption, keeping the amount', async () => {
    const user = userEvent.setup()
    await run(user, replay.cases['FAIR-003'])
    const receipt = screen.getByTestId('future-receipt')
    expect(receipt).toHaveTextContent('Expected first payment')
    expect(receipt).not.toHaveTextContent('Due now (at signup)')
    expect(receipt).not.toHaveTextContent('at signup')
    expect(screen.getByTestId('due-now')).toHaveTextContent('9.99 USD')
    expect(screen.getByTestId('due-timing-note')).toHaveTextContent('FAIR has not verified when this is charged')
    expect(screen.getByTestId('due-timing-note').querySelector('[data-provenance="assumption"]')).not.toBeNull()
    expect(screen.getByTestId('next-charge')).toHaveTextContent('9.99 USD, timing assumed')
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('119.88 USD')
  })

  it('does the same in Arabic', async () => {
    const user = userEvent.setup()
    await run(user, replay.cases['FAIR-003'], 'ar')
    const receipt = screen.getByTestId('future-receipt')
    expect(receipt).toHaveTextContent('الدفعة الأولى المتوقعة')
    expect(receipt).not.toHaveTextContent('المستحق الآن (عند التسجيل)')
    expect(screen.getByTestId('due-now')).toHaveTextContent('9.99 USD')
    expect(screen.getByTestId('due-timing-note')).toHaveTextContent('لم يتحقق FAIR من موعد الخصم')
    expect(screen.getByTestId('next-charge')).toHaveTextContent('التوقيت مفترض')
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('119.88 USD')
  })

  it('keeps the plain label for a free trial with nothing to pay', async () => {
    const user = userEvent.setup()
    await run(user, liveResponse('decision-twin'))
    const receipt = screen.getByTestId('future-receipt')
    expect(receipt).toHaveTextContent('Due now (at signup)')
    expect(screen.getByTestId('due-now')).toHaveTextContent('0.00 USD')
    expect(screen.queryByTestId('due-timing-note')).not.toBeInTheDocument()
    expect(screen.getByTestId('next-charge')).toHaveTextContent('9.99 USD, expected on day 7')
  })

  it('labels a signup fee during a free trial as assumed too', async () => {
    const user = userEvent.setup()
    await run(user, liveResponse())
    expect(screen.getByTestId('due-now')).toHaveTextContent('2.50 USD')
    expect(screen.getByTestId('due-timing-note')).toBeInTheDocument()
  })

  it('labels the older cost card the same way', async () => {
    const user = userEvent.setup()
    const { decision, claims, claims_summary, ...legacy } = replay.cases['FAIR-003'].body
    await run(user, { ...replay.cases['FAIR-003'], body: legacy })
    expect(screen.getByTestId('due-timing-note')).toHaveTextContent('FAIR has not verified when this is charged')
  })
})

describe('replay mode is never presented as live', () => {
  const REPLAY = { ...HEALTH.live, model: 'replay:muse-spark-1.3' }

  it.each([
    ['en', 'Replay mode, not live', 'Recorded synthetic example — replay, not a live model request.', 'no model request was made', 'Live analysis'],
    ['ar', 'وضع الإعادة، ليس مباشرًا', 'مثال اصطناعي مسجَّل — إعادة عرض، وليس طلبًا مباشرًا إلى النموذج.', 'لم يُرسل أي طلب إلى النموذج', 'تحليل مباشر'],
  ])('labels the status, the note and the result (%s)', async (lang, pill, badge, notice, liveWords) => {
    const user = userEvent.setup()
    const { terms, expectation, body } = replay.cases['FAIR-003']
    mockFetchWith(REPLAY, fakeResponse(200, { ...body, model: 'replay:muse-spark-1.3' }))
    renderApp(lang)
    await waitFor(() => expect(screen.getByTestId('status-pill')).toHaveAttribute('data-status', 'replay'))
    expect(screen.getByTestId('status-pill')).toHaveTextContent(pill)
    expect(screen.getByTestId('availability')).toHaveAttribute('data-status', 'replay')
    const [termsLabel, expectationLabel, button] = lang === 'en' ? ['Subscription terms', 'Your expectation', ANALYZE] : ['شروط الاشتراك', 'توقعك', 'اكشف الفجوة']
    await user.click(screen.getByLabelText(termsLabel))
    await user.paste(terms)
    await user.click(screen.getByLabelText(expectationLabel))
    await user.paste(expectation)
    await user.click(screen.getByRole('button', { name: button }))
    expect(await screen.findByTestId('replay-badge')).toHaveTextContent(badge)
    expect(screen.getByTestId('replay-notice')).toHaveTextContent(notice)
    expect(screen.queryByTestId('live-badge')).not.toBeInTheDocument()
    expect(document.body).not.toHaveTextContent(liveWords)
    expect(document.body).not.toHaveTextContent('replay:')
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('119.88 USD')
  })

  it('a normal model name still shows the live badge', async () => {
    const user = userEvent.setup()
    const { terms, expectation, body } = replay.cases['FAIR-003']
    mockFetch(fakeResponse(200, body))
    renderApp()
    await fillAndSubmit(user, terms, expectation)
    await screen.findByTestId('live-badge')
    expect(screen.queryByTestId('replay-badge')).not.toBeInTheDocument()
  })
})

describe('things the user must be able to see', () => {
  it('Show in source scrolls to the quote even when several findings share its sentence', async () => {
    const user = userEvent.setup()
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    try {
      const { terms, expectation, body } = replay.cases['FAIR-003']
      mockFetch(fakeResponse(200, body))
      renderApp()
      await fillAndSubmit(user, terms, expectation)
      await screen.findByTestId('live-badge')
      scroll.mockClear()
      await user.click(screen.getByRole('button', { name: 'Show in source text' }))
      expect(scroll).toHaveBeenCalledTimes(1)
      const target = scroll.mock.contexts[0]
      expect(target.tagName).toBe('MARK')
      expect(target).toHaveAttribute('data-active', 'true')
      expect(target).toHaveTextContent('at least 48 hours before the next renewal date')
    } finally {
      delete Element.prototype.scrollIntoView
    }
  })

  it('brings an error into view, because on a phone it renders below the form', async () => {
    const user = userEvent.setup()
    const scroll = vi.fn()
    Element.prototype.scrollIntoView = scroll
    try {
      mockFetch(fakeResponse(503, { error: { code: 'live_calls_disabled', message: 'x' } }))
      renderApp()
      await fillAndSubmit(user, 'Some terms.', 'A belief.')
      const alert = await screen.findByRole('alert')
      expect(scroll.mock.contexts).toContain(alert)
    } finally {
      delete Element.prototype.scrollIntoView
    }
  })

  it('shows the model name without forcing Arabic labels into a left-to-right monospace run', async () => {
    const user = userEvent.setup()
    const { terms, expectation, body } = replay.cases['FAIR-003']
    mockFetch(fakeResponse(200, body))
    renderApp('ar')
    await user.click(screen.getByLabelText('شروط الاشتراك'))
    await user.paste(terms)
    await user.click(screen.getByLabelText('توقعك'))
    await user.paste(expectation)
    await user.click(screen.getByRole('button', { name: 'اكشف الفجوة' }))
    await screen.findByTestId('live-badge')
    const model = screen.getByText(/النموذج: muse-spark-1\.3/)
    expect(model).not.toHaveAttribute('dir', 'ltr')
    expect(model.className).not.toContain('font-mono')
  })
})

describe('workspace shell and navigation', () => {
  it('opens on the Analyze workspace with the tool immediately visible', () => {
    mockFetch()
    renderApp()
    expect(window.location.hash).toBe('#/analyze')
    expect(screen.getByRole('heading', { level: 1, name: 'Analyze an offer' })).toBeInTheDocument()
    expect(screen.getByText('Find the gap between what you expect and what the terms actually say.')).toBeInTheDocument()
    expect(screen.getByLabelText('Subscription terms')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: ANALYZE })).toBeInTheDocument()
    expect(nav('Analyze')).toHaveAttribute('aria-current', 'page')
  })

  it('removes the public demo clutter', () => {
    mockFetch()
    renderApp()
    expect(screen.queryByText("The fine print shouldn't be a surprise.")).not.toBeInTheDocument()
    expect(screen.queryByText('Sample gallery')).not.toBeInTheDocument()
    expect(screen.queryByText('How FAIR stays honest')).not.toBeInTheDocument()
    expect(screen.queryByText(/Sample Preview/)).not.toBeInTheDocument()
    // One short disclaimer in the shell, not repeated across the page.
    expect(screen.getAllByText(/not legal or financial advice/)).toHaveLength(1)
  })

  it('locks Results until an analysis exists', async () => {
    const user = userEvent.setup()
    mockFetch()
    renderApp()
    const results = nav('Results')
    expect(results).toHaveAttribute('aria-disabled', 'true')
    await user.click(results)
    expect(screen.getByTestId('view-analyze')).toBeInTheDocument()
    expect(window.location.hash).toBe('#/analyze')
  })

  it('navigates without reloading and keeps the inputs', async () => {
    const user = userEvent.setup()
    mockFetch()
    renderApp()
    await user.type(screen.getByLabelText('Subscription terms'), 'USD 5 per month')
    await user.type(screen.getByLabelText('Your expectation'), 'cheap')
    await user.click(nav('About FAIR'))
    expect(screen.getByRole('heading', { level: 1, name: 'About FAIR' })).toHaveFocus()
    expect(window.location.hash).toBe('#/about')
    expect(screen.getByTestId('workspace-title')).toHaveTextContent('About FAIR')
    await user.click(nav('Analyze'))
    expect(screen.getByLabelText('Subscription terms')).toHaveValue('USD 5 per month')
    expect(screen.getByLabelText('Your expectation')).toHaveValue('cheap')
  })

  it('follows browser back/forward via the hash', async () => {
    mockFetch()
    renderApp()
    act(() => {
      window.location.hash = '#/about'
    })
    await waitFor(() => expect(screen.getByTestId('view-about')).toBeInTheDocument())
    act(() => {
      window.location.hash = '#/analyze'
    })
    await waitFor(() => expect(screen.getByTestId('view-analyze')).toBeInTheDocument())
  })

  it('redirects a #/results link to Analyze when there is no result', async () => {
    window.history.replaceState(null, '', '/#/results')
    mockFetch()
    renderApp()
    expect(screen.getByTestId('view-analyze')).toBeInTheDocument()
    expect(window.location.hash).toBe('#/analyze')
  })

  it('About explains the product, its limitations and privacy without status claims', async () => {
    const user = userEvent.setup()
    mockFetch()
    renderApp()
    await user.click(nav('About FAIR'))
    const about = screen.getByTestId('view-about')
    expect(within(about).getByRole('heading', { name: 'Limitations' })).toBeInTheDocument()
    expect(within(about).getByRole('heading', { name: 'Privacy' })).toBeInTheDocument()
    expect(about).toHaveTextContent('The FAIR server does not store your text.')
    expect(about).toHaveTextContent('not legal or financial advice')
  })

  it('mobile drawer opens as a dialog, closes with Escape, and returns focus', async () => {
    const user = userEvent.setup()
    mockFetch()
    renderApp()
    const menu = screen.getByRole('button', { name: 'Open navigation' })
    await user.click(menu)
    const dialog = screen.getByRole('dialog', { name: 'Main navigation' })
    expect(within(dialog).getByRole('button', { name: /^Analyze/ })).toHaveFocus()
    await user.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(menu).toHaveFocus()
  })

  it('mobile drawer navigates and closes', async () => {
    const user = userEvent.setup()
    mockFetch()
    renderApp()
    await user.click(screen.getByRole('button', { name: 'Open navigation' }))
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^About FAIR/ }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByTestId('view-about')).toBeInTheDocument()
  })
})

describe('truthful system status', () => {
  it.each([
    [HEALTH.notConfigured, 'not_configured', 'Live AI not configured', /no Meta API key is configured/],
    [HEALTH.disabled, 'disabled', 'Live AI turned off', /turned off on this server/],
    [null, 'unreachable', 'Server unreachable', /cannot be reached/],
  ])('shows an honest unavailable state (%#)', async (health, status, pill, note) => {
    mockFetchWith(health)
    renderApp()
    await waitFor(() => expect(screen.getByTestId('status-pill')).toHaveAttribute('data-status', status))
    expect(screen.getByTestId('status-pill')).toHaveTextContent(pill)
    expect(screen.getByTestId('availability')).toHaveTextContent(note)
    expect(screen.queryByText(/Analysis by Meta Muse Spark/)).not.toBeInTheDocument()
  })

  it('renders exactly one status region', async () => {
    mockFetch()
    renderApp()
    await waitFor(() => expect(screen.getAllByTestId('status-pill')).toHaveLength(1))
  })

  it('mentions Muse Spark as the engine only when the server reports live access', async () => {
    mockFetchWith(HEALTH.live)
    renderApp()
    await waitFor(() => expect(screen.getByTestId('status-pill')).toHaveAttribute('data-status', 'live'))
    expect(screen.getByTestId('status-pill')).toHaveTextContent('Live AI on')
    expect(screen.getByTestId('availability')).toHaveTextContent('Analysis by Meta Muse Spark')
    expect(screen.getByTestId('availability')).toHaveTextContent('muse-spark-1.3')
  })
})

describe('form validation', () => {
  it('shows field errors and does not call the API when inputs are empty', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch()
    renderApp()
    await user.click(screen.getByRole('button', { name: ANALYZE }))
    expect(screen.getByText('Please paste the offer terms.')).toBeInTheDocument()
    expect(screen.getByText('Please describe what you expect.')).toBeInTheDocument()
    expect(screen.getByLabelText('Subscription terms')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Subscription terms')).toHaveFocus()
    expect(analyzeCalls(fetchMock)).toHaveLength(0)
  })

  it('treats whitespace-only input as empty', async () => {
    const user = userEvent.setup()
    const fetchMock = mockFetch()
    renderApp()
    await fillAndSubmit(user, '   ', 'ok')
    expect(screen.getByText('Please paste the offer terms.')).toBeInTheDocument()
    expect(analyzeCalls(fetchMock)).toHaveLength(0)
  })

  it('rejects over-long expectations', async () => {
    const user = userEvent.setup()
    mockFetch()
    renderApp()
    await user.type(screen.getByLabelText('Subscription terms'), 'terms')
    await user.click(screen.getByLabelText('Your expectation'))
    await user.paste('x'.repeat(2001))
    await user.click(screen.getByRole('button', { name: ANALYZE }))
    expect(screen.getByText('Your expectation is too long (maximum 2,000 characters).')).toBeInTheDocument()
  })

  it('shows server-side field validation errors (422)', async () => {
    const user = userEvent.setup()
    mockFetch(
      fakeResponse(422, {
        error: { code: 'invalid_request', message: 'The request body is invalid.', details: [{ field: 'terms', message: 'String too long', type: 'x' }] },
      }),
    )
    renderApp()
    await fillAndSubmit(user, 'some terms', 'some expectation')
    expect(await screen.findByText('Please check your input')).toBeInTheDocument()
    expect(screen.getByText('The server could not accept this field: String too long')).toBeInTheDocument()
  })
})

describe('language and direction', () => {
  it('switches to Arabic RTL (sidebar mirrors via logical start) and back', async () => {
    const user = userEvent.setup()
    mockFetch()
    renderApp()
    expect(screen.getByTestId('sidebar')).toHaveClass('start-0')
    await user.click(screen.getByRole('button', { name: 'Switch the interface to Arabic' }))
    expect(document.documentElement).toHaveAttribute('dir', 'rtl')
    expect(document.documentElement).toHaveAttribute('lang', 'ar')
    expect(screen.getByRole('heading', { level: 1, name: 'افحص عرضًا' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'اكشف الفجوة' })).toBeInTheDocument()
    expect(within(screen.getByTestId('sidebar')).getByRole('button', { name: /^عن FAIR/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'تبديل الواجهة إلى الإنجليزية' }))
    expect(document.documentElement).toHaveAttribute('dir', 'ltr')
  })

  it('preserves inputs, view and results when switching language', async () => {
    const user = userEvent.setup()
    await analyzeLive(user)
    await user.click(screen.getByRole('button', { name: 'Switch the interface to Arabic' }))
    expect(screen.getByTestId('view-results')).toBeInTheDocument()
    expect(screen.getByTestId('live-badge')).toHaveTextContent('تحليل مباشر')
    expect(screen.getByTestId('verdict')).toHaveTextContent('تعارض')
    expect(screen.getByText(/لا يبقى مجانيًا/)).toBeInTheDocument() // Arabic explanation from the response
    expect(screen.getByRole('region', { name: 'الإيصال المستقبلي' })).toHaveTextContent('الإجمالي خلال 12 شهرًا')
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent(/146[.٫]38 USD/)
    expect(screen.getByRole('region', { name: 'مرآة التوقعات' })).toHaveTextContent('تُحاسَب تلقائيًا بعد التجربة')
    await user.click(within(screen.getByTestId('sidebar')).getByRole('button', { name: /^التحليل/ }))
    expect(screen.getByLabelText('شروط الاشتراك')).toHaveValue(liveResponse().terms)
  })
})

describe('live analysis → Results workspace', () => {
  it('calls the real endpoint and opens Results on success', async () => {
    const user = userEvent.setup()
    const { fetchMock } = await analyzeLive(user)
    const [[url, init]] = analyzeCalls(fetchMock)
    expect(url).toBe('/api/analyze')
    expect(JSON.parse(init.body).language).toBe('en')
    expect(window.location.hash).toBe('#/results')
    expect(screen.getByRole('heading', { level: 1, name: 'Results' })).toHaveFocus()
    expect(nav('Results')).toHaveAttribute('aria-current', 'page')
    expect(screen.getByText('Model: muse-spark-1.3')).toBeInTheDocument()
    expect(screen.queryByTestId('preview-badge')).not.toBeInTheDocument()
  })

  it('keeps results while visiting other views in the session', async () => {
    const user = userEvent.setup()
    await analyzeLive(user)
    await user.click(nav('About FAIR'))
    await user.click(nav('Analyze'))
    expect(screen.getByRole('button', { name: 'View latest result' })).toBeInTheDocument()
    await user.click(nav('Results'))
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'CONTRADICTION')
  })

  it('leads with the overall verdict, then the Expectation Mirror claim by claim', async () => {
    const user = userEvent.setup()
    await analyzeLive(user)
    const verdict = screen.getByTestId('verdict')
    expect(verdict).toHaveTextContent('Contradiction')
    expect(verdict).toHaveTextContent('The terms contradict your expectation')
    expect(verdict).toHaveTextContent('It does not stay free.')
    expect(within(verdict).getByText('AI interpretation')).toBeInTheDocument()
    const mirror = screen.getByRole('region', { name: 'Expectation Mirror' })
    const claims = within(mirror).getAllByTestId('claim')
    expect(claims.map((c) => c.dataset.verdict)).toEqual(['MATCH', 'CONTRADICTION'])
    expect(claims[0]).toHaveTextContent('“I can try it for free.”')
    expect(within(claims[1]).getByText(/renews automatically at USD 11.99/).tagName).toBe('MARK')
    await user.click(within(claims[1]).getByRole('button', { name: 'Show in source text' }))
    const active = screen.getByTestId('source-text').querySelectorAll('mark[data-active="true"]')
    expect([...active].map((m) => m.textContent).join('')).toContain('After the trial')
  })

  it('Future Receipt shows backend amounts for each horizon and both paths', async () => {
    const user = userEvent.setup()
    await analyzeLive(user)
    const receipt = screen.getByRole('region', { name: 'Future Receipt' })
    expect(within(receipt).getByTestId('next-charge')).toHaveTextContent('11.99 USD, expected on day 14')
    expect(within(receipt).getByTestId('due-now')).toHaveTextContent('2.50 USD')
    const horizon = within(receipt).getByTestId('horizon-switch')
    expect(within(horizon).getByRole('button', { name: '12 months' })).toHaveAttribute('aria-pressed', 'true')
    for (const [label, total, diff] of [['1 month', '14.49 USD', '11.99 USD'], ['3 months', '38.47 USD', '35.97 USD'], ['12 months', '146.38 USD', '143.88 USD']]) {
      await user.click(within(horizon).getByRole('button', { name: label }))
      expect(within(horizon).getByRole('button', { name: label })).toHaveAttribute('aria-pressed', 'true')
      expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent(total)
      expect(screen.getByTestId('receipt-total-cancel')).toHaveTextContent('2.50 USD') // only the signup fee
      expect(screen.getByTestId('receipt-difference')).toHaveTextContent(`Difference between the two paths: ${diff}`)
    }
    const keep = screen.getByTestId('receipt-continue')
    expect(keep).toHaveAttribute('data-status', 'complete')
    expect(keep).toHaveTextContent('Monthly charge × 12')
    expect(keep).toHaveTextContent('One-time fee: activation fee')
    expect(keep).toHaveTextContent('Assumes you do not cancel during this period.')
  })

  it('cancel path is conditional, shows the documented deadline, and never assumes free cancellation or refunds', async () => {
    const user = userEvent.setup()
    await analyzeLive(user)
    const cancel = screen.getByTestId('receipt-cancel')
    expect(cancel).toHaveAttribute('data-status', 'conditional')
    expect(within(cancel).getByTestId('receipt-deadline')).toHaveTextContent('At least 24 hours before the free trial ends (day 14)')
    expect(cancel).toHaveTextContent('FAIR cannot confirm that cancelling is free.')
    expect(cancel).toHaveTextContent('No refund is assumed.')
    expect(screen.getByTestId('receipt-difference')).toHaveTextContent('A calculation, not a promise')
    // Every amount links to the verified quote it came from.
    await user.click(within(cancel).getByRole('button', { name: 'Show the source for One-time fee: activation fee' }))
    const active = screen.getByTestId('source-text').querySelectorAll('mark[data-active="true"]')
    expect([...active].map((m) => m.textContent).join('')).toContain('A one-time activation fee of USD 2.50')
  })

  it('highlights verified evidence and lists each quoted sentence once', async () => {
    const user = userEvent.setup()
    const { live } = await analyzeLive(user)
    const source = screen.getByTestId('source-text')
    expect(source).toHaveTextContent(live.terms)
    expect([...source.querySelectorAll('mark')].map((m) => m.textContent).join('')).toContain(
      'A one-time activation fee of USD 2.50 is charged when you sign up.',
    )
    const quotes = within(screen.getByTestId('verified-evidence')).getAllByRole('button').map((b) => b.querySelector('q').textContent)
    expect(new Set(quotes).size).toBe(quotes.length) // no repeated quote cards
    expect(screen.getByTestId('verified-evidence')).toHaveTextContent('Currency · Recurring price · Billing period')
  })

  it('keeps extracted terms behind a closed disclosure, still reachable', async () => {
    const user = userEvent.setup()
    await analyzeLive(user)
    const disclosure = screen.getByTestId('details-disclosure')
    expect(disclosure).not.toHaveAttribute('open')
    await user.click(within(disclosure).getByText('Extracted terms'))
    expect(disclosure).toHaveAttribute('open')
    const details = screen.getByRole('region', { name: 'Extracted terms' })
    expect(within(details).getByText('14 days')).toBeInTheDocument()
    await user.click(within(details).getByRole('button', { name: 'Show the quote for Free trial' }))
    const active = screen.getByTestId('source-text').querySelectorAll('mark[data-active="true"]')
    expect([...active].map((m) => m.textContent).join('')).toContain('free for 14 days.')
  })

  it('states when nothing material is uncertain', async () => {
    const user = userEvent.setup()
    await analyzeLive(user)
    expect(screen.getByTestId('uncertain')).toHaveTextContent('Nothing material is missing')
    expect(screen.queryByTestId('unverified-evidence')).not.toBeInTheDocument()
  })

  it('UNKNOWN with missing information is explicit and never confident', async () => {
    const user = userEvent.setup()
    await analyzeLive(user, 'missing-details')
    const verdict = screen.getByTestId('verdict')
    expect(verdict).toHaveAttribute('data-verdict', 'UNKNOWN')
    expect(verdict).toHaveTextContent('Not stated')
    expect(verdict).toHaveTextContent("The terms don't settle this")
    const uncertain = screen.getByTestId('uncertain')
    expect(within(uncertain).getByTestId('not-stated')).toHaveTextContent('FAIR could not confirm these from the terms: Billing period, Automatic renewal, Cancellation rules')
    expect(uncertain).toHaveTextContent('Some cost projections rely on assumptions or missing values.')
    const keep = screen.getByTestId('receipt-continue')
    for (const label of ['1 month', '3 months', '12 months']) {
      await user.click(within(screen.getByTestId('horizon-switch')).getByRole('button', { name: label }))
      expect(keep).toHaveAttribute('data-status', 'unavailable')
      expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('—')
      expect(keep).toHaveTextContent('Missing: billing period')
      expect(keep.textContent).not.toMatch(/\d+\.\d\d/)
    }
    expect(screen.getByTestId('receipt-unavailable-cancel')).toHaveTextContent('The terms do not say the plan renews automatically')
    expect(screen.queryByTestId('receipt-difference')).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Future Receipt' })).toHaveTextContent('No automatic charge identified')
    const claims = within(screen.getByTestId('mirror')).getAllByTestId('claim')
    expect(claims.map((c) => c.dataset.verdict)).toEqual(['UNKNOWN', 'UNKNOWN'])
    expect(within(claims[1]).getByTestId('claim-no-evidence')).toHaveTextContent('No sentence in the terms settles this claim.')
  })

  it('rejected claims are separate from verified evidence and shown open when they changed the verdict', async () => {
    const user = userEvent.setup()
    await analyzeLive(user, 'evidence-guard')
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'UNKNOWN')
    expect(screen.getByTestId('downgraded')).toHaveTextContent('The model answered "Match"')
    // Claim level: the model cited a REAL sentence that is not about refunds; FAIR overrules it.
    const [refund] = within(screen.getByTestId('mirror')).getAllByTestId('claim')
    expect(refund).toHaveAttribute('data-verdict', 'UNKNOWN')
    expect(within(refund).getByTestId('claim-downgraded')).toHaveTextContent('Cited sentence is not about this claim')
    expect(within(refund).getByTestId('claim-no-evidence')).toBeInTheDocument()
    expect(refund).not.toHaveTextContent('renews automatically')

    const evidence = screen.getByRole('region', { name: 'Verified evidence' })
    expect(evidence).not.toHaveTextContent('Refunds are given')
    expect(evidence).not.toHaveTextContent(/service fee/i)

    const uncertain = screen.getByTestId('uncertain')
    expect(uncertain).toHaveTextContent('Rejected model claims: 2')
    expect(uncertain.querySelector('details')).toHaveAttribute('open')
    const rejected = within(uncertain).getByTestId('unverified-evidence')
    expect(rejected).toHaveTextContent('“Refunds are given for unused days.”')
    expect(rejected).toHaveTextContent('“A service fee of 5 SAR applies.”')
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('348.00 SAR')
    expect(screen.getByTestId('receipt-continue')).not.toHaveTextContent(/service fee/i) // invented fee never priced
  })

  it('shows conditional projections with prominent assumptions', async () => {
    const user = userEvent.setup()
    await analyzeLive(user, 'intro-price-ar')
    await user.click(within(screen.getByTestId('horizon-switch')).getByRole('button', { name: '3 months' }))
    const keep = screen.getByTestId('receipt-continue')
    expect(keep).toHaveAttribute('data-status', 'conditional')
    expect(keep).toHaveTextContent('Depends on assumptions')
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('105.00 SAR')
    expect(keep).toHaveTextContent('The introductory price is assumed to last one billing period')
  })

  it('Decision Twin: a composite expectation becomes separate claims with mixed outcomes', async () => {
    const user = userEvent.setup()
    await analyzeLive(user, 'decision-twin')
    const claims = within(screen.getByTestId('mirror')).getAllByTestId('claim')
    expect(claims.map((c) => c.textContent.match(/“([^”]+)”/)[1])).toEqual([
      'The trial is free.',
      'The subscription ends automatically.',
      'I can cancel whenever I want.',
    ])
    expect(claims.map((c) => c.dataset.verdict)).toEqual(['MATCH', 'CONTRADICTION', 'UNKNOWN'])
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'CONTRADICTION')
    expect(screen.getByTestId('receipt-total-cancel')).toHaveTextContent('0.00 USD')
    expect(screen.getByTestId('receipt-deadline')).toHaveTextContent('At least 48 hours before the free trial ends (day 7)')
    expect(screen.getByTestId('receipt-total-continue')).toHaveTextContent('119.88 USD')
    expect(screen.getByTestId('verified-evidence')).toHaveTextContent('Claim 1')
    // An unsettled claim is material uncertainty: never "nothing is missing".
    const uncertain = screen.getByTestId('uncertain')
    expect(within(uncertain).getByTestId('unsettled-claims')).toHaveTextContent('Claims the terms do not settle: 1')
    expect(uncertain).not.toHaveTextContent('Nothing material is missing')
  })

  it('Decision Twin in Arabic: claims, receipt and deadline are translated', async () => {
    const user = userEvent.setup()
    const live = liveResponse('decision-twin')
    mockFetch(fakeResponse(200, live.body))
    renderApp('ar')
    await user.click(screen.getByLabelText('شروط الاشتراك'))
    await user.paste(live.terms)
    await user.click(screen.getByLabelText('توقعك'))
    await user.paste(live.expectation)
    await user.click(screen.getByRole('button', { name: 'اكشف الفجوة' }))
    await screen.findByTestId('live-badge')
    const mirror = screen.getByRole('region', { name: 'مرآة التوقعات' })
    expect(within(mirror).getAllByTestId('claim').map((c) => c.dataset.verdict)).toEqual(['MATCH', 'CONTRADICTION', 'UNKNOWN'])
    expect(mirror).toHaveTextContent('غير محسوم')
    expect(screen.getByTestId('receipt-deadline')).toHaveTextContent('قبل انتهاء الفترة التجريبية المجانية بـ48 ساعة على الأقل (اليوم 7)')
    expect(screen.getByTestId('receipt-cancel')).toHaveTextContent('لا يستطيع FAIR تأكيد أن الإلغاء مجاني')
  })

  it('separates the last safe cancellation day from the trial end', async () => {
    const user = userEvent.setup()
    await analyzeLive(user, 'decision-twin')
    const deadline = screen.getByTestId('receipt-deadline')
    expect(within(deadline).getByTestId('deadline-last-safe')).toHaveTextContent(/Last safe day to cancel: ≈ .+ \(day 5\) if you sign up today/)
    expect(within(deadline).getByTestId('deadline-trial-end')).toHaveTextContent(/Trial ends: ≈ .+ if you sign up today/)
    expect(within(deadline).getByTestId('deadline-note')).toHaveTextContent('Calculated from the trial length and notice period')
    expect(deadline.querySelector('[data-provenance="calc"]')).not.toBeNull()
  })

  it('rounds a partial day down, so the safe date is never later than the terms allow', async () => {
    const user = userEvent.setup()
    const live = liveResponse('decision-twin')
    live.body.decision.cancel_path.deadline = { kind: 'trial_end', day: 7, notice: { amount: 36, unit: 'hours' }, last_safe_hour: 132 }
    mockFetch(fakeResponse(200, live.body))
    renderApp()
    await fillAndSubmit(user, live.terms, live.expectation)
    await screen.findByTestId('live-badge')
    expect(screen.getByTestId('deadline-last-safe')).toHaveTextContent('(day 5)')
  })

  it('shows the last safe day in Arabic', async () => {
    const user = userEvent.setup()
    const live = liveResponse('decision-twin')
    mockFetch(fakeResponse(200, live.body))
    renderApp('ar')
    await user.click(screen.getByLabelText('شروط الاشتراك'))
    await user.paste(live.terms)
    await user.click(screen.getByLabelText('توقعك'))
    await user.paste(live.expectation)
    await user.click(screen.getByRole('button', { name: 'اكشف الفجوة' }))
    await screen.findByTestId('live-badge')
    expect(screen.getByTestId('deadline-last-safe')).toHaveTextContent('آخر يوم آمن للإلغاء')
    expect(screen.getByTestId('deadline-last-safe')).toHaveTextContent('(اليوم 5)')
    expect(screen.getByTestId('deadline-trial-end')).toHaveTextContent('تنتهي التجربة')
  })

  it.each([
    ['no notice', { kind: 'trial_end', day: 7, notice: null, last_safe_hour: null }],
    ['an older response', { kind: 'trial_end', day: 7, notice: null }],
  ])('never invents a last safe day for %s', async (_name, deadline) => {
    const user = userEvent.setup()
    const live = liveResponse('decision-twin')
    live.body.decision.cancel_path.deadline = deadline
    mockFetch(fakeResponse(200, live.body))
    renderApp()
    await fillAndSubmit(user, live.terms, live.expectation)
    await screen.findByTestId('live-badge')
    expect(screen.queryByTestId('deadline-last-safe')).not.toBeInTheDocument()
    expect(screen.getByTestId('deadline-note')).toHaveTextContent('does not calculate a last safe day')
  })

  it.each([
    ['an unreadable claim', { dropped: 1, omitted_amounts: 0 }],
    ['an amount no claim checked', { dropped: 0, omitted_amounts: 1 }],
  ])('tells the user when %s stopped a full match', async (_name, gaps) => {
    const user = userEvent.setup()
    const live = liveResponse('decision-twin')
    mockFetch(fakeResponse(200, { ...live.body, claims_summary: { ...live.body.claims_summary, overall: 'UNKNOWN', ...gaps } }))
    renderApp()
    await fillAndSubmit(user, live.terms, live.expectation)
    await screen.findByTestId('live-badge')
    expect(screen.getByTestId('mirror-incomplete')).toHaveTextContent('does not present it as a full match')
  })

  it('shows no incomplete notice when every claim was read and every amount checked', async () => {
    const user = userEvent.setup()
    await analyzeLive(user, 'decision-twin')
    expect(screen.queryByTestId('mirror-incomplete')).not.toBeInTheDocument()
  })

  it.each([
    ['en', 'The cited sentence does not make this promise', 'Closest text in the terms'],
    ['ar', 'الجملة المستشهد بها لا تقدّم هذا الوعد', 'أقرب نص في الشروط'],
  ])('an unsupported promise is not shown as confirmed (%s)', async (lang, reason, closest) => {
    const user = userEvent.setup()
    const live = liveResponse('decision-twin')
    const promise = { ...live.body.claims[0], verdict: 'UNKNOWN', model_verdict: 'MATCH', downgraded: true, reason: 'absolute_claim_unsupported', evidence_role: null }
    mockFetch(fakeResponse(200, { ...live.body, verdict: 'MATCH', claims: [promise], claims_summary: { overall: 'UNKNOWN', counts: { MATCH: 0, CONTRADICTION: 0, UNKNOWN: 1 }, dropped: 0, omitted_amounts: 0 } }))
    renderApp(lang)
    const [terms, expectation, button] = lang === 'en' ? ['Subscription terms', 'Your expectation', ANALYZE] : ['شروط الاشتراك', 'توقعك', 'اكشف الفجوة']
    await user.click(screen.getByLabelText(terms))
    await user.paste(live.terms)
    await user.click(screen.getByLabelText(expectation))
    await user.paste(live.expectation)
    await user.click(screen.getByRole('button', { name: button }))
    await screen.findByTestId('live-badge')
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'UNKNOWN')
    expect(screen.getByTestId('claim-downgraded')).toHaveTextContent(reason)
    expect(screen.getByTestId('claim')).toHaveTextContent(closest)
    expect(screen.getByTestId('claim').querySelector('[data-provenance="terms"]')).toBeNull()
  })

  it('explains an overall match that has no claim-level support', async () => {
    const user = userEvent.setup()
    const live = liveResponse('decision-twin')
    const overall = {
      ...live.body.claims[0],
      text: live.expectation,
      verdict: 'UNKNOWN',
      model_verdict: 'MATCH',
      downgraded: true,
      reason: 'no_claim_support',
      from_overall: true,
    }
    mockFetch(fakeResponse(200, { ...live.body, verdict: 'MATCH', claims: [overall], claims_summary: { overall: 'UNKNOWN', counts: { MATCH: 0, CONTRADICTION: 0, UNKNOWN: 1 }, dropped: 0, omitted_amounts: 0 } }))
    renderApp()
    await fillAndSubmit(user, live.terms, live.expectation)
    await screen.findByTestId('live-badge')
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'UNKNOWN')
    expect(screen.getByTestId('claim-downgraded')).toHaveTextContent('The model gave an overall match with no claim-by-claim support')
  })

  it('labels a quote under an UNKNOWN claim as closest text, not as a verified finding', async () => {
    const user = userEvent.setup()
    await analyzeLive(user, 'decision-twin')
    const [match, , unknown] = within(screen.getByTestId('mirror')).getAllByTestId('claim')
    expect(unknown).toHaveTextContent('Closest text in the terms')
    expect(unknown).not.toHaveTextContent('The terms say')
    expect(within(unknown).getByTestId('claim-closest')).toHaveTextContent('does not settle the claim')
    expect(unknown.querySelector('[data-provenance="terms"]')).toBeNull()
    expect(unknown.querySelector('[data-provenance="unknown"]')).not.toBeNull()
    expect(match).toHaveTextContent('The terms say')
    expect(match.querySelector('[data-provenance="terms"]')).not.toBeNull()
    expect(screen.getByTestId('verified-evidence')).toHaveTextContent('Claim 3 (closest text, does not settle it)')
  })

  it("shows the user's own words above the claims, so a short claim stays understandable", async () => {
    const user = userEvent.setup()
    const { live } = await analyzeLive(user, 'decision-twin')
    expect(screen.getByTestId('mirror-original')).toHaveTextContent(live.expectation)
  })

  it('falls back to the previous cards for a response without claims or decision (backward compatible)', async () => {
    const user = userEvent.setup()
    const live = liveResponse()
    const { claims, claims_summary, decision, ...legacy } = live.body
    mockFetch(fakeResponse(200, legacy))
    renderApp()
    await fillAndSubmit(user, live.terms, live.expectation)
    await screen.findByTestId('live-badge')
    expect(screen.queryByTestId('mirror')).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Expectation vs reality' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Financial impact' })).toBeInTheDocument()
    expect(screen.getByTestId('projection-12')).toHaveTextContent('146.38 USD')
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'CONTRADICTION')
  })

  it('flags when the model overall reading differs from the claim-by-claim result', async () => {
    const user = userEvent.setup()
    const live = liveResponse('decision-twin')
    mockFetch(fakeResponse(200, { ...live.body, verdict: 'MATCH' }))
    renderApp()
    await fillAndSubmit(user, live.terms, live.expectation)
    await screen.findByTestId('live-badge')
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'CONTRADICTION')
    expect(screen.getByTestId('overall-differs')).toHaveTextContent('differs from the claim-by-claim result')
  })

  it('Edit inputs returns to Analyze with the submitted text', async () => {
    const user = userEvent.setup()
    const { live } = await analyzeLive(user)
    await user.click(screen.getByRole('button', { name: 'Edit inputs' }))
    expect(screen.getByTestId('view-analyze')).toBeInTheDocument()
    expect(screen.getByLabelText('Subscription terms')).toHaveValue(live.terms)
  })
})

describe('errors never produce results', () => {
  it.each([
    ['model_not_configured', "Live analysis isn't set up yet"],
    ['live_calls_disabled', 'Live analysis is turned off'],
  ])('%s: honest message, stays on Analyze, Results stays locked', async (code, title) => {
    const user = userEvent.setup()
    mockFetch(fakeResponse(503, { error: { code, message: 'MODEL_API_KEY is not set on the server.' } }))
    renderApp()
    await fillAndSubmit(user, 'Free for 7 days.', 'free forever')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(title)
    expect(alert).toHaveTextContent(`Error code: ${code}`)
    expect(alert).not.toHaveTextContent('MODEL_API_KEY')
    expect(screen.getByTestId('view-analyze')).toBeInTheDocument()
    expect(nav('Results')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByTestId('verdict')).not.toBeInTheDocument()
  })

  it('shows the configuration error in Arabic', async () => {
    const user = userEvent.setup()
    mockFetch(fakeResponse(503, { error: { code: 'model_not_configured', message: 'x' } }))
    renderApp('ar')
    await user.type(screen.getByLabelText('شروط الاشتراك'), 'نص')
    await user.type(screen.getByLabelText('توقعك'), 'توقع')
    await user.click(screen.getByRole('button', { name: 'اكشف الفجوة' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('التحليل المباشر غير مُعدّ بعد')
  })

  it('a failed re-analysis clears the previous result', async () => {
    const user = userEvent.setup()
    const live = liveResponse()
    mockFetch(fakeResponse(200, live.body), fakeResponse(502, { error: { code: 'model_unavailable', message: 'x' } }))
    renderApp()
    await fillAndSubmit(user, live.terms, live.expectation)
    await screen.findByTestId('live-badge')
    await user.click(screen.getByRole('button', { name: 'Edit inputs' }))
    await user.click(screen.getByRole('button', { name: ANALYZE }))
    expect(await screen.findByRole('alert')).toHaveTextContent('The Meta API is unavailable')
    expect(nav('Results')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByRole('button', { name: 'View latest result' })).not.toBeInTheDocument()
  })

  it('upstream failure can be retried into a result', async () => {
    const user = userEvent.setup()
    const live = liveResponse()
    const fetchMock = mockFetch(
      fakeResponse(502, { error: { code: 'model_unavailable', message: 'Could not connect to the Meta API.' } }),
      fakeResponse(200, live.body),
    )
    renderApp()
    await fillAndSubmit(user, live.terms, live.expectation)
    expect(await screen.findByRole('alert')).toHaveTextContent('The Meta API is unavailable')
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    await screen.findByTestId('live-badge')
    expect(analyzeCalls(fetchMock)).toHaveLength(2)
  })

  it('explains the rate limit in both languages', async () => {
    const user = userEvent.setup()
    mockFetch(fakeResponse(429, { error: { code: 'rate_limited', message: 'x' } }))
    renderApp()
    await fillAndSubmit(user, 'terms', 'expectation')
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many requests')
    await user.click(screen.getByRole('button', { name: 'Switch the interface to Arabic' }))
    expect(screen.getByRole('alert')).toHaveTextContent('طلبات كثيرة جدًا')
  })

  it('shows server detail only for an unrecognised error code', async () => {
    const user = userEvent.setup()
    mockFetch(fakeResponse(500, { error: { code: 'brand_new_code', message: 'Something specific happened.' } }))
    renderApp()
    await fillAndSubmit(user, 'terms', 'expectation')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Unexpected response')
    expect(alert).toHaveTextContent('Something specific happened.')
  })

  it('shows a reachability error when the backend is down', async () => {
    const user = userEvent.setup()
    mockFetch(fakeResponse(502))
    renderApp()
    await fillAndSubmit(user, 'terms', 'expectation')
    expect(await screen.findByRole('alert')).toHaveTextContent("Can't reach the FAIR server")
  })

  it('shows loading, and Cancel aborts without an error or result', async () => {
    const user = userEvent.setup()
    vi.stubGlobal(
      'fetch',
      vi.fn((url, init) =>
        String(url).endsWith('/api/health')
          ? Promise.resolve(fakeResponse(200, HEALTH.notConfigured))
          : new Promise((_, reject) => init.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))),
      ),
    )
    renderApp()
    await fillAndSubmit(user, 'terms', 'expectation')
    expect(screen.getByTestId('loading')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Revealing the gap…' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    await waitFor(() => expect(screen.queryByTestId('loading')).not.toBeInTheDocument())
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(screen.getByTestId('view-analyze')).toBeInTheDocument()
  })
})

describe('development-only sample previews', () => {
  it('?sample=<id> opens a labeled preview without calling the API', async () => {
    window.history.replaceState(null, '', '/?sample=evidence-guard')
    const fetchMock = mockFetch()
    renderApp()
    const badge = await screen.findByTestId('preview-badge')
    expect(badge).toHaveTextContent('Sample Preview — Not AI Generated')
    expect(screen.queryByTestId('live-badge')).not.toBeInTheDocument()
    expect(screen.queryByText(/muse-spark/)).not.toBeInTheDocument()
    expect(analyzeCalls(fetchMock)).toHaveLength(0)
    expect(screen.getByTestId('verdict')).toHaveAttribute('data-verdict', 'UNKNOWN')
  })

  it('closing the preview returns to Analyze and locks Results', async () => {
    const user = userEvent.setup()
    window.history.replaceState(null, '', '/?sample=trial-autorenew')
    mockFetch()
    renderApp()
    await screen.findByTestId('preview-badge')
    await user.click(screen.getByRole('button', { name: 'Close preview' }))
    expect(screen.getByTestId('view-analyze')).toBeInTheDocument()
    expect(nav('Results')).toHaveAttribute('aria-disabled', 'true')
  })
})

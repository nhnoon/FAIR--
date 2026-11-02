// Turn an AnalyzeResponse into display-ready evidence items.
// Only items whose backend evidence.verified === true are ever shown as verified
// or highlighted. Everything else goes to the "could not be verified" list.

export function factEvidenceId(field) {
  return `fact-${field}`
}

export function collectEvidence(data) {
  const items = []
  if (data.verdict_evidence) {
    items.push({ id: 'verdict', field: 'verdict', evidence: data.verdict_evidence })
  }
  for (const f of data.facts || []) {
    items.push({ id: factEvidenceId(f.field), field: f.field, value: f.value, evidence: f.evidence })
  }
  ;(data.extracted_terms?.one_time_fees || []).forEach((fee, i) => {
    items.push({ id: `fee-${i}`, field: 'one_time_fee', label: fee.label, value: fee.amount, evidence: fee.evidence })
  })
  // Claim evidence (Expectation Mirror): only quotes the backend verified for that claim.
  ;(data.claims || []).forEach((c, i) => {
    if (c.evidence?.verified) items.push({ id: c.id || `claim-${i + 1}`, field: 'claim', label: String(i + 1), unsettled: c.verdict === 'UNKNOWN', evidence: c.evidence })
  })
  ;(data.rejected_facts || []).forEach((f, i) => {
    const [field, label] = String(f.field).split(/:(.*)/s)
    items.push({ id: `rejected-${i}`, field, label, value: f.value, evidence: f.evidence, rejected: true })
  })

  const isVerified = (it) => it.evidence?.verified === true && !it.rejected
  const verified = items.filter(isVerified)
  const unverified = items.filter((it) => !isVerified(it))
  return { verified, unverified }
}

/** Human label for an evidence item, consistent with the details rows. */
export function evidenceFieldLabel(t, item, billingPeriod) {
  if (item.field === 'verdict') return t('evidence.verdictQuote')
  if (item.field === 'claim') return t(item.unsettled ? 'mirror.claimClosest' : 'mirror.claimN', { n: item.label })
  if (item.field === 'one_time_fee') return t('fields.one_time_fee', { label: item.label || '' })
  // No stated period means the price is not presented as recurring.
  if (item.field === 'recurring_price' && billingPeriod === 'unknown') return t('details.price')
  const label = t(`fields.${item.field}`)
  return label === `fields.${item.field}` ? item.field : label
}

/** Key terms that are absent from the verified extraction. */
export function missingKeyTerms(extracted) {
  const missing = []
  if (extracted.recurring_price == null) missing.push('recurring_price')
  if (extracted.billing_period === 'unknown') missing.push('billing_period')
  if (extracted.auto_renewal === 'not_stated') missing.push('auto_renewal')
  if (!extracted.cancellation_requirement) missing.push('cancellation_requirement')
  if (!extracted.currency) missing.push('currency')
  return missing
}

/** Evidence-item id for the verified fact behind a receipt line (backend source_field). */
export function sourceFieldEvidenceId(sourceField) {
  if (!sourceField) return null
  const fee = String(sourceField).match(/^fee:(\d+)$/)
  return fee ? `fee-${fee[1]}` : factEvidenceId(sourceField)
}

/** Highlight ranges for the source text, from verified items only. */
export function highlightRanges(verifiedItems) {
  return verifiedItems
    .filter((it) => Number.isInteger(it.evidence.start) && Number.isInteger(it.evidence.end))
    .map((it) => ({ id: it.id, start: it.evidence.start, end: it.evidence.end }))
}

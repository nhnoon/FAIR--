import { useLang } from '../i18n/LanguageContext.jsx'
import { quote } from '../lib/format.js'
import { ProvenanceLegend, ProvenanceTag } from './Provenance.jsx'
import { AlertIcon, CheckIcon, QuestionIcon, QuoteIcon, XIcon } from './icons.jsx'

// Each verdict: own colour + icon + word (colour is never the only signal).
const STYLE = {
  MATCH: { chip: 'bg-match-bg text-match-fg ring-match-line', mark: 'bg-match-line', Icon: CheckIcon },
  CONTRADICTION: { chip: 'bg-contra-bg text-contra-fg ring-contra-line', mark: 'bg-contra-line', Icon: XIcon },
  UNKNOWN: { chip: 'bg-unknown-bg text-unknown-fg ring-unknown-line', mark: 'bg-unknown-line', Icon: QuestionIcon },
}

function ClaimRow({ claim, index, onShowEvidence }) {
  const { t, lang } = useLang()
  const s = STYLE[claim.verdict]
  // A quote under UNKNOWN exists in the terms but does not decide the claim.
  const decides = claim.verdict !== 'UNKNOWN' && claim.evidence?.verified
  return (
    <li className="rounded-xl border border-line p-4" data-testid="claim" data-verdict={claim.verdict} data-downgraded={claim.downgraded || undefined}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="text-xs font-semibold text-muted">{t('mirror.claimN', { n: index + 1 })}</p>
        <span className={`chip ${s.chip}`}>
          <s.Icon width={12} height={12} />
          {t(`mirror.verdict.${claim.verdict}`)}
        </span>
      </div>

      <div className="mt-2 grid gap-3 md:grid-cols-2">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted">{t('mirror.youBelieve')}</p>
          <p dir="auto" className="mt-0.5 break-words font-medium text-fg">
            {quote(claim.text, lang)}
          </p>
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted">{t(claim.verdict === 'UNKNOWN' && claim.evidence?.verified ? 'mirror.closestText' : 'mirror.termsSay')}</p>
          {claim.evidence?.verified ? (
            <>
              <p dir="auto" className="mt-0.5 break-words text-fg">
                <mark className={`rounded px-1 text-fg ${s.mark}`}>{quote(claim.evidence.quote, lang)}</mark>
              </p>
              {decides ? null : (
                <p className="mt-1 text-xs text-muted" data-testid="claim-closest">
                  {t('mirror.closestNote')}
                </p>
              )}
              <button type="button" className="text-link-btn mt-1" onClick={() => onShowEvidence(claim.id)}>
                <QuoteIcon width={13} height={13} />
                {t('mirror.showInSource')}
              </button>
            </>
          ) : (
            <p className="mt-0.5 text-sm text-muted" data-testid="claim-no-evidence">
              {t('mirror.noEvidence')}
            </p>
          )}
        </div>
      </div>

      <p className="mt-3 break-words text-sm text-fg" lang={lang}>
        {claim.explanation[lang]}
      </p>

      {claim.downgraded ? (
        <p className="mt-2 flex gap-1.5 text-xs text-unknown-fg" data-testid="claim-downgraded">
          <AlertIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>
            {t('mirror.modelSaid', { verdict: t(`mirror.verdict.${claim.model_verdict}`), shown: t(`mirror.verdict.${claim.verdict}`) })}{' '}
            <span className="font-semibold">{t(`mirror.reasons.${claim.reason}`)}</span>
          </span>
        </p>
      ) : null}

      <div className="mt-3 flex flex-wrap gap-1.5">
        <ProvenanceTag kind="ai" />
        {decides ? <ProvenanceTag kind="terms" /> : <ProvenanceTag kind="unknown" />}
      </div>
    </li>
  )
}

export default function ExpectationMirror({ data, expectation, onShowEvidence }) {
  const { t, lang } = useLang()
  const claims = data.claims || []
  const overall = data.claims_summary?.overall
  return (
    <section aria-labelledby="mirror-heading" className="card p-5 sm:p-6" data-testid="mirror">
      <h2 id="mirror-heading" className="section-title">
        {t('mirror.title')}
      </h2>
      <p className="mt-0.5 text-sm text-muted">{t('mirror.subtitle')}</p>
      <div className="mt-3">
        <ProvenanceLegend />
      </div>
      {overall && overall !== data.verdict ? (
        <p className="mt-3 rounded-lg bg-subtle p-3 text-xs text-muted" data-testid="overall-differs">
          {t('mirror.overallDiffers', { verdict: t(`mirror.verdict.${data.verdict}`) })}
        </p>
      ) : null}
      {data.claims_summary?.dropped || data.claims_summary?.omitted_amounts ? (
        <p className="mt-3 flex gap-1.5 rounded-lg bg-unknown-bg p-3 text-xs text-unknown-fg" data-testid="mirror-incomplete">
          <AlertIcon width={14} height={14} className="mt-0.5 shrink-0" />
          <span>{t('mirror.incomplete')}</span>
        </p>
      ) : null}
      {expectation && !claims[0]?.from_overall ? (
        <div className="mt-3 rounded-lg bg-subtle p-3" data-testid="mirror-original">
          <p className="text-xs font-medium text-muted">{t('compare.youExpected')}</p>
          <p dir="auto" className="mt-0.5 break-words text-sm text-fg">
            {quote(expectation, lang)}
          </p>
        </div>
      ) : null}
      <ol className="mt-4 space-y-3">
        {claims.map((c, i) => (
          <ClaimRow key={c.id} claim={c} index={i} onShowEvidence={onShowEvidence} />
        ))}
      </ol>
    </section>
  )
}

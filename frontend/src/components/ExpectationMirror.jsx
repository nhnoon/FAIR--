import { useLang } from '../i18n/LanguageContext.jsx'
import { quote } from '../lib/format.js'
import Chapter from './Chapter.jsx'
import { ProvenanceTag } from './Provenance.jsx'
import { CheckIcon, QuestionIcon, XIcon } from './icons.jsx'

// Each verdict: own colour + icon + word (colour is never the only signal).
const STYLE = {
  MATCH: { chip: 'text-match-fg', mark: 'bg-hl-match', rule: 'border-match-solid', Icon: CheckIcon },
  CONTRADICTION: { chip: 'text-contra-fg', mark: 'bg-hl-contra', rule: 'border-contra-solid', Icon: XIcon },
  UNKNOWN: { chip: 'text-unknown-fg', mark: 'bg-hl-unknown', rule: 'border-unknown-solid', Icon: QuestionIcon },
}

function ClaimRow({ claim, index, onShowEvidence }) {
  const { t, lang } = useLang()
  const s = STYLE[claim.verdict]
  // A quote under UNKNOWN exists in the terms but does not decide the claim.
  const decides = claim.verdict !== 'UNKNOWN' && claim.evidence?.verified
  return (
    <li className={`border-s-2 ps-4 sm:ps-5 ${s.rule}`} data-testid="claim" data-verdict={claim.verdict} data-downgraded={claim.downgraded || undefined}>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <span className={`chip font-semibold ${s.chip}`}>
          <s.Icon width={12} height={12} />
          {t(`mirror.verdict.${claim.verdict}`)}
        </span>
        <p className="text-xs text-muted">{t('mirror.claimN', { n: index + 1 })}</p>
      </div>

      <div className="mt-3 grid gap-4 md:grid-cols-2 md:gap-6">
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
              <p dir="auto" className="quote-text mt-0.5 break-words text-paper-fg">
                <mark className={`box-decoration-clone rounded-sm px-1 text-paper-fg ${s.mark}`}>{quote(claim.evidence.quote, lang)}</mark>
              </p>
              {decides ? null : (
                <p className="mt-1 text-xs text-muted" data-testid="claim-closest">
                  {t('mirror.closestNote')}
                </p>
              )}
              <button type="button" className="text-link-btn mt-1" onClick={() => onShowEvidence(claim.id)}>
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
        <p className="mt-2 text-xs text-unknown-fg" data-testid="claim-downgraded">
          <span>
            {t('mirror.modelSaid', { verdict: t(`mirror.verdict.${claim.model_verdict}`), shown: t(`mirror.verdict.${claim.verdict}`) })}{' '}
            <span className="font-semibold">{t(`mirror.reasons.${claim.reason}`)}</span>
          </span>
        </p>
      ) : null}

      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
        <ProvenanceTag kind="ai" />
        {decides ? <ProvenanceTag kind="terms" /> : <ProvenanceTag kind="unknown" />}
      </div>
    </li>
  )
}

export default function ExpectationMirror({ data, onShowEvidence }) {
  const { t } = useLang()
  const claims = data.claims || []
  const overall = data.claims_summary?.overall
  return (
    <Chapter id="mirror-heading" title={t('mirror.title')} testId="mirror">
      {overall && overall !== data.verdict ? (
        <p className="mb-5 text-xs text-muted" data-testid="overall-differs">
          {t('mirror.overallDiffers', { verdict: t(`mirror.verdict.${data.verdict}`) })}
        </p>
      ) : null}
      {data.claims_summary?.dropped || data.claims_summary?.omitted_amounts ? (
        <p className="mb-5 border-s-2 border-unknown-solid ps-3 text-sm text-unknown-fg" data-testid="mirror-incomplete">
          {t('mirror.incomplete')}
        </p>
      ) : null}
      <ol className="space-y-5">
        {claims.map((c, i) => (
          <ClaimRow key={c.id} claim={c} index={i} onShowEvidence={onShowEvidence} />
        ))}
      </ol>
    </Chapter>
  )
}

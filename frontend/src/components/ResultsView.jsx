import { forwardRef, useState } from 'react'
import { isReplayModel } from '../api/client.js'
import { useLang } from '../i18n/LanguageContext.jsx'
import { quote } from '../lib/format.js'
import CostBreakdown from './CostBreakdown.jsx'
import DecisionReveal from './DecisionReveal.jsx'
import ExpectationMirror from './ExpectationMirror.jsx'
import FutureReceipt from './FutureReceipt.jsx'
import { ProvenanceTag } from './Provenance.jsx'
import EvidenceViewer from './EvidenceViewer.jsx'
import TermsDetails from './TermsDetails.jsx'
import UncertaintyPanel from './UncertaintyPanel.jsx'
import { AlertIcon, CheckIcon, FlaskIcon, QuestionIcon, QuoteIcon, ShieldIcon, XIcon } from './icons.jsx'

// Each verdict has its own colour, icon and word, so colour is never the only signal.
const VERDICT_STYLE = {
  MATCH: { box: 'border-match-line bg-match-bg', icon: 'bg-match-solid', tag: 'text-match-fg', text: 'text-match-fg', mark: 'bg-match-line', Icon: CheckIcon },
  CONTRADICTION: { box: 'border-contra-line bg-contra-bg', icon: 'bg-contra-solid', tag: 'text-contra-fg', text: 'text-contra-fg', mark: 'bg-contra-line', Icon: XIcon },
  UNKNOWN: { box: 'border-unknown-line bg-unknown-bg', icon: 'bg-unknown-solid', tag: 'text-unknown-fg', text: 'text-unknown-fg', mark: 'bg-unknown-line', Icon: QuestionIcon },
}

function ModeBadge({ result }) {
  const { t } = useLang()
  if (result.kind === 'preview') {
    return (
      <span className="chip bg-unknown-bg text-unknown-fg ring-unknown-line" data-testid="preview-badge">
        <FlaskIcon width={13} height={13} />
        {t('preview.badge')}
      </span>
    )
  }
  if (isReplayModel(result.data.model)) {
    return (
      <span className="chip bg-unknown-bg text-unknown-fg ring-unknown-line" data-testid="replay-badge">
        <FlaskIcon width={13} height={13} />
        {t('replay.badge')}
      </span>
    )
  }
  return (
    <span className="flex flex-wrap items-center gap-2">
      <span className="chip bg-primary text-primary-fg ring-primary">
        <ShieldIcon width={13} height={13} />
        <span data-testid="live-badge">{t('live.badge')}</span>
      </span>
      <span className="text-xs text-muted">
        {t('live.model', { model: result.data.model })}
      </span>
    </span>
  )
}

function VerdictCard({ data }) {
  const { t, lang } = useLang()
  // Overall = claim-by-claim result (CONTRADICTION if any claim is contradicted, UNKNOWN if any is unsettled).
  const overall = data.claims_summary?.overall || data.verdict
  const s = VERDICT_STYLE[overall]
  return (
    <section aria-labelledby="verdict-heading" className={`rounded-2xl border p-5 sm:p-6 ${s.box}`} data-testid="verdict" data-verdict={overall}>
      <div className="flex items-start gap-4">
        <span className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl text-on-solid ${s.icon}`}>
          <s.Icon width={24} height={24} />
        </span>
        <div className="min-w-0">
          <p className={`eyebrow ${s.tag}`}>{t('verdict.label')}</p>
          <h2 id="verdict-heading" className={`mt-0.5 text-2xl font-bold leading-tight sm:text-3xl ${s.text}`}>
            {t(`verdict.${overall}.tag`)}
          </h2>
          <p className={`mt-1 font-medium ${s.text}`}>{t(`verdict.${overall}.headline`)}</p>
        </div>
      </div>
      <div className="mt-4 rounded-xl bg-surface/80 p-4">
        <p className="text-xs font-semibold text-muted">{t('verdict.why')}</p>
        <p className="mt-1 break-words leading-relaxed text-fg" lang={lang}>
          {data.explanation[lang]}
        </p>
        <div className="mt-2">
          <ProvenanceTag kind="ai" />
        </div>
      </div>
      {data.verdict_downgraded ? (
        <p className="mt-3 flex gap-2 rounded-xl bg-surface/80 p-3 text-sm text-unknown-fg" data-testid="downgraded">
          <AlertIcon width={18} height={18} className="mt-0.5 shrink-0 text-unknown-fg" />
          <span>{t('verdict.downgraded', { verdict: t(`verdict.words.${data.model_verdict}`) })}</span>
        </p>
      ) : null}
    </section>
  )
}

function CompareCard({ result, onShowQuote }) {
  const { t, lang } = useLang()
  const ev = result.data.verdict_evidence
  const verified = ev?.verified === true
  const s = VERDICT_STYLE[result.data.verdict]
  return (
    <section aria-labelledby="compare-heading" className="card p-5 sm:p-6" data-testid="comparison">
      <h2 id="compare-heading" className="section-title">
        {t('compare.title')}
      </h2>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div className="min-w-0 rounded-xl bg-subtle p-4">
          <p className="text-xs font-semibold text-muted">{t('compare.youExpected')}</p>
          <p dir="auto" className="mt-1.5 break-words font-medium text-fg">
            {quote(result.expectation, lang)}
          </p>
        </div>
        <div className="min-w-0 rounded-xl border border-line p-4">
          <p className="text-xs font-semibold text-muted">{t('compare.termsEstablish')}</p>
          {verified ? (
            <>
              <p dir="auto" className="mt-1.5 break-words font-medium text-fg">
                <mark className={`rounded px-1 text-fg ${s.mark}`}>{quote(ev.quote, lang)}</mark>
              </p>
              <button
                type="button"
                onClick={onShowQuote}
                className="mt-2 inline-flex min-h-[32px] items-center gap-1 rounded-md px-2 text-xs font-semibold text-link hover:bg-subtle"
              >
                <QuoteIcon width={14} height={14} />
                {t('compare.showInSource')}
              </button>
            </>
          ) : (
            <p className="mt-1.5 text-sm text-muted" data-testid="no-deciding-quote">
              {t('compare.noEvidence')}
            </p>
          )}
        </div>
      </div>
    </section>
  )
}

const ResultsView = forwardRef(function ResultsView({ result, onEdit, onClosePreview }, headingRef) {
  const { t } = useLang()
  const [activeId, setActiveId] = useState(null)

  if (!result) {
    return (
      <div className="card p-8 text-center" data-testid="results-empty">
        <h1 ref={headingRef} tabIndex={-1} className="text-lg font-semibold text-fg focus:outline-none">
          {t('results.emptyTitle')}
        </h1>
        <p className="mt-1 text-sm text-muted">{t('results.emptyBody')}</p>
        <button type="button" className="btn-primary mt-5" onClick={onEdit}>
          {t('results.goAnalyze')}
        </button>
      </div>
    )
  }

  const { data } = result
  return (
    <article className="space-y-5" data-kind={result.kind} aria-labelledby="results-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 space-y-1.5">
          <h1 id="results-heading" ref={headingRef} tabIndex={-1} className="text-2xl font-bold text-fg focus:outline-none">
            {t('results.title')}
          </h1>
          <ModeBadge result={result} />
        </div>
        <div className="flex gap-2">
          {result.kind === 'preview' ? (
            <button type="button" className="btn-ghost" onClick={onClosePreview}>
              {t('preview.close')}
            </button>
          ) : null}
          <button type="button" className="btn-secondary" onClick={onEdit}>
            {t('results.editInputs')}
          </button>
        </div>
      </div>

      {result.kind === 'preview' ? (
        <p className="rounded-xl border border-dashed border-unknown-line bg-unknown-bg px-4 py-3 text-sm text-unknown-fg">{t('preview.notice')}</p>
      ) : null}

      {isReplayModel(data.model) ? (
        <p className="rounded-xl border border-dashed border-unknown-line bg-unknown-bg px-4 py-3 text-sm text-unknown-fg" data-testid="replay-notice">
          {t('replay.notice')}
        </p>
      ) : null}

      <VerdictCard data={data} />
      <DecisionReveal key={result.id} data={data} onShowEvidence={setActiveId} />
      {/* Older responses without claims/decision fall back to the previous cards. */}
      {data.claims?.length ? (
        <ExpectationMirror data={data} expectation={result.expectation} onShowEvidence={setActiveId} />
      ) : (
        <CompareCard result={result} onShowQuote={() => setActiveId('verdict')} />
      )}
      {data.decision ? <FutureReceipt data={data} onShowEvidence={setActiveId} /> : <CostBreakdown cost={data.cost} />}
      <EvidenceViewer data={data} sourceText={result.terms} activeId={activeId} onActivate={setActiveId} />
      <UncertaintyPanel data={data} />
      <TermsDetails data={data} onShowEvidence={setActiveId} />
    </article>
  )
})

export default ResultsView

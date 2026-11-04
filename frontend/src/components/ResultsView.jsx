import { forwardRef, useMemo, useState } from 'react'
import { isEarlierPromptReplay, isReplayModel } from '../api/client.js'
import { useLang } from '../i18n/LanguageContext.jsx'
import { overallVerdict } from '../lib/evidence.js'
import { quote } from '../lib/format.js'
import Chapter, { SectionsContext } from './Chapter.jsx'
import CostBreakdown from './CostBreakdown.jsx'
import DecisionReveal, { canReveal } from './DecisionReveal.jsx'
import EvidenceViewer from './EvidenceViewer.jsx'
import ExpectationMirror from './ExpectationMirror.jsx'
import FutureReceipt from './FutureReceipt.jsx'
import ResultCard from './ResultCard.jsx'
import TermsDetails from './TermsDetails.jsx'
import TrustAudit from './TrustAudit.jsx'
import UncertaintyPanel, { hasUncertainty } from './UncertaintyPanel.jsx'

function ModeLine({ result }) {
  const { t } = useLang()
  const { data } = result
  if (result.kind === 'preview') {
    return (
      <div className="rounded-xl bg-unknown-bg px-4 py-2.5 text-sm text-unknown-fg">
        <p className="font-semibold" data-testid="preview-badge">{t('preview.badge')}</p>
        <p>{t('preview.notice')}</p>
      </div>
    )
  }
  // One line, attached to this result: a recorded answer must never read as a new live one.
  if (isReplayModel(data.model)) {
    return (
      <div className="text-xs text-muted">
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="chip whitespace-nowrap font-medium text-unknown-fg" data-testid="replay-badge">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-unknown-solid" />
            {t('replay.badge')}
          </span>
          <span data-testid="replay-notice">{t(result.kind === 'saved' ? 'replay.savedNotice' : 'replay.notice')}</span>
        </p>
        {isEarlierPromptReplay(data.model) ? <p className="mt-2 text-sm font-medium text-unknown-fg" data-testid="earlier-prompt-notice">{t('replay.earlierPrompt')}</p> : null}
      </div>
    )
  }
  return (
    <p className="text-xs text-muted">
      <span className="font-medium text-fg" data-testid="live-badge">{t('live.badge')}</span> · <span>{t('live.model', { model: data.model })}</span>
    </p>
  )
}

function CompareDetail({ result, onShowQuote }) {
  const { t, lang } = useLang()
  const ev = result.data.verdict_evidence
  const verified = ev?.verified === true
  return (
    <Chapter id="compare-heading" title={t('compare.title')} testId="comparison">
      <p className="text-xs font-medium text-muted">{t('compare.termsEstablish')}</p>
      {verified ? (
        <>
          <p dir="auto" className="mt-1 break-words text-fg">
            <mark className="rounded bg-mark px-1 text-fg">{quote(ev.quote, lang)}</mark>
          </p>
          <button type="button" onClick={onShowQuote} className="text-link-btn mt-1">
            {t('compare.showInSource')}
          </button>
        </>
      ) : (
        <p className="mt-1 text-sm text-muted" data-testid="no-deciding-quote">
          {t('compare.noEvidence')}
        </p>
      )}
    </Chapter>
  )
}

const ResultsView = forwardRef(function ResultsView({ result, onEdit, onNew, onClosePreview }, headingRef) {
  const { t } = useLang()
  const [activeId, setActiveId] = useState(null)
  // A material limitation is never left closed: this row starts open whenever there is any uncertainty.
  const [open, setOpenState] = useState(() => (result && hasUncertainty(result.data) ? { 'uncertain-heading': true } : {}))
  const sections = useMemo(() => ({ isOpen: (id) => !!open[id], setOpen: (id, value) => setOpenState((s) => (!!s[id] === value ? s : { ...s, [id]: value })) }), [open])

  if (!result) {
    return (
      <div className="page py-20 text-center" data-testid="results-empty">
        <h1 ref={headingRef} tabIndex={-1} className="text-3xl font-semibold tracking-tight text-fg focus:outline-none">
          {t('results.emptyTitle')}
        </h1>
        <p className="mt-2 text-muted">{t('results.emptyBody')}</p>
        <button type="button" className="btn-primary mt-6" onClick={onEdit}>
          {t('results.goAnalyze')}
        </button>
      </div>
    )
  }

  const { data } = result
  const hasOptions = canReveal(data)
  const jump = (id) => {
    sections.setOpen(id, true)
    requestAnimationFrame(() => document.getElementById(`section-${id}`)?.scrollIntoView?.({ behavior: 'smooth', block: 'start' }))
  }
  const showEvidence = (id) => {
    sections.setOpen('evidence-heading', true)
    setActiveId(id)
  }
  const firstDetail = data.claims?.length ? 'mirror-heading' : 'compare-heading'

  return (
    <SectionsContext.Provider value={sections}>
      <article className="page space-y-5 pb-16 pt-5 sm:pt-6" data-kind={result.kind} aria-labelledby="results-heading">
        <h1 id="results-heading" ref={headingRef} tabIndex={-1} className="sr-only">
          {t('results.title')}
        </h1>
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          <div className="min-w-0 flex-1 basis-72">
            <ModeLine result={result} />
          </div>
          <div className="flex shrink-0 gap-1">
            {result.kind === 'preview' ? (
              <button type="button" className="btn-ghost" onClick={onClosePreview}>
                {t('preview.close')}
              </button>
            ) : null}
            <button type="button" className="btn-ghost" onClick={onEdit}>
              {t('results.editInputs')}
            </button>
            <button type="button" className="btn-ghost" onClick={onNew}>
              {t('results.newCheck')}
            </button>
          </div>
        </div>

        <section aria-labelledby="verdict-heading" data-testid="verdict" data-verdict={overallVerdict(data)} className="rise">
          <ResultCard
            data={data}
            expectation={result.expectation}
            onShowEvidence={showEvidence}
            actions={
              <>
                {hasOptions ? (
                  <button type="button" className="btn-primary flex-1 whitespace-nowrap" onClick={() => jump('reveal-heading')}>
                    {t('result.explore')}
                  </button>
                ) : null}
                <button type="button" className={`${hasOptions ? 'btn-secondary' : 'btn-primary'} flex-1 whitespace-nowrap`} onClick={() => jump(firstDetail)}>
                  {t('result.details')}
                </button>
              </>
            }
          />
        </section>

        <div className="rounded-3xl border border-line bg-surface" data-testid="result-details">
          {hasOptions ? <DecisionReveal key={result.id} data={data} onShowEvidence={showEvidence} /> : null}
          {data.claims?.length ? <ExpectationMirror data={data} onShowEvidence={showEvidence} /> : <CompareDetail result={result} onShowQuote={() => showEvidence('verdict')} />}
          {data.decision ? (
            <FutureReceipt data={data} onShowEvidence={showEvidence} />
          ) : (
            <Chapter id="cost-detail-heading" title={t('receipt.title')}>
              <CostBreakdown cost={data.cost} />
            </Chapter>
          )}
          <EvidenceViewer data={data} sourceText={result.terms} activeId={activeId} onActivate={setActiveId} />
          <UncertaintyPanel data={data} />
          {data.claims?.length && result.kind !== 'preview' ? <TrustAudit data={data} /> : null}
          <TermsDetails data={data} onShowEvidence={showEvidence} />
        </div>
      </article>
    </SectionsContext.Provider>
  )
})

export default ResultsView

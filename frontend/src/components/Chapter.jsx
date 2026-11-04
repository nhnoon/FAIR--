import { createContext, useContext } from 'react'
import { ChevronIcon } from './icons.jsx'

// ResultsView owns which detail rows are open, so an action in the answer can open the row it points to.
export const SectionsContext = createContext(null)

/** One expandable row under the answer. Its content stays in the page, so nothing is lost by closing it. */
export default function Chapter({ id, title, testId, attrs, children }) {
  const sections = useContext(SectionsContext)
  return (
    <section id={`section-${id}`} aria-labelledby={id} data-testid={testId} {...attrs} className="scroll-mt-24 border-b border-line last:border-b-0">
      <details className="group" open={sections?.isOpen(id) || undefined} onToggle={(e) => sections?.setOpen(id, e.currentTarget.open)}>
        <summary className="flex min-h-[60px] cursor-pointer list-none items-center justify-between gap-3 rounded-lg px-5 sm:px-6">
          <h2 id={id} className="text-base font-semibold text-fg">
            {title}
          </h2>
          <ChevronIcon width={18} height={18} className="shrink-0 text-muted transition-transform group-open:rotate-180" />
        </summary>
        <div className="min-w-0 px-5 pb-6 pt-1 sm:px-6">{children}</div>
      </details>
    </section>
  )
}

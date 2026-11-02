// Small inline icons (decorative: aria-hidden). Stroke uses currentColor.
const base = {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
  focusable: 'false',
}

export const CheckIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M20 6 9 17l-5-5" />
  </svg>
)
export const XIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M18 6 6 18M6 6l12 12" />
  </svg>
)
export const QuestionIcon = (p) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17h.01" />
  </svg>
)
export const AlertIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01" />
  </svg>
)
export const ShieldIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <path d="m9 12 2 2 4-4" />
  </svg>
)
export const QuoteIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M7 7h4v4H8a1 1 0 0 0-1 1v5M14 7h4v4h-3a1 1 0 0 0-1 1v5" />
  </svg>
)
export const GlobeIcon = (p) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
  </svg>
)
export const FlaskIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M9 3h6M10 3v6L4.5 18.5A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.5L14 9V3" />
  </svg>
)
export const CalculatorIcon = (p) => (
  <svg {...base} {...p}>
    <rect x="5" y="3" width="14" height="18" rx="2" />
    <path d="M8 7h8M8 12h.01M12 12h.01M16 12h.01M8 16h.01M12 16h.01M16 16h.01" />
  </svg>
)
export const LanguagesIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M4 5h8M8 3v2M6 5c0 4 2 7 6 9M10 5c0 3-2 6-6 8M13 21l4-10 4 10M14.5 17h5" />
  </svg>
)
export const ScaleIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M12 3v18M7 21h10M5 7h14M5 7l-3 7a3 3 0 0 0 6 0L5 7zM19 7l-3 7a3 3 0 0 0 6 0l-3-7z" />
  </svg>
)
export const ArrowIcon = (p) => (
  <svg {...base} {...p} className={`rtl:-scale-x-100 ${p?.className || ''}`}>
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
)
export const MinusIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M5 12h14" />
  </svg>
)
export const MenuIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M4 6h16M4 12h16M4 18h16" />
  </svg>
)
export const SearchIcon = (p) => (
  <svg {...base} {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="m20 20-3.5-3.5" />
  </svg>
)
export const ListIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" />
  </svg>
)
export const InfoIcon = (p) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8h.01" />
  </svg>
)
export const ChevronIcon = (p) => (
  <svg {...base} {...p}>
    <path d="m6 9 6 6 6-6" />
  </svg>
)
export const Spinner = (p) => (
  <svg {...base} {...p} className={`motion-safe:animate-spin ${p?.className || ''}`}>
    <path d="M21 12a9 9 0 1 1-6.2-8.6" />
  </svg>
)

export const SunIcon = (p) => (
  <svg {...base} {...p}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
)
export const MoonIcon = (p) => (
  <svg {...base} {...p}>
    <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
  </svg>
)
export const MonitorIcon = (p) => (
  <svg {...base} {...p}>
    <rect x="3" y="4" width="18" height="12" rx="2" />
    <path d="M8 20h8M12 16v4" />
  </svg>
)

/** FAIR mark: expectation and terms as two offset bars with a visible gap. Navy brand, works on both themes. */
export const FairMark = ({ size = 36 }) => (
  <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" focusable="false">
    <rect width="40" height="40" rx="11" fill="#F4F6FB" />
    <rect x="9" y="9" width="8" height="22" rx="3" fill="#111D35" />
    <rect x="23" y="14" width="8" height="17" rx="3" fill="#5B6F96" />
  </svg>
)

/** @type {import('tailwindcss').Config} */

// Semantic colour tokens. Values live in src/index.css as RGB channels per theme
// (:root = light, .dark = dark), so components never reference raw palette colours.
const token = (name) => `rgb(var(--c-${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: token('bg'),
        surface: token('surface'),
        subtle: token('subtle'),
        fg: token('fg'),
        muted: token('muted'),
        line: token('line'),
        primary: { DEFAULT: token('primary'), hover: token('primary-hover'), fg: token('on-primary') },
        link: token('link'),
        mark: { DEFAULT: token('mark'), active: token('mark-active') },
        focus: token('focus'),
        // The home hero, and the tinted block that anything quoted from the terms sits on.
        ink: { DEFAULT: token('ink'), fg: token('ink-fg'), muted: token('ink-muted'), line: token('ink-line') },
        paper: { DEFAULT: token('paper'), fg: token('paper-fg'), muted: token('paper-muted'), line: token('paper-line') },
        hl: { match: token('hl-match'), contra: token('hl-contra'), unknown: token('hl-unknown') },
        // Verdict / status colours: kept separate from the navy brand.
        match: { bg: token('match-bg'), fg: token('match-fg'), line: token('match-line'), solid: token('match-solid') },
        contra: { bg: token('contra-bg'), fg: token('contra-fg'), line: token('contra-line'), solid: token('contra-solid') },
        unknown: { bg: token('unknown-bg'), fg: token('unknown-fg'), line: token('unknown-line'), solid: token('unknown-solid') },
        'on-solid': token('on-solid'),
      },
      fontFamily: {
        sans: ['Inter', '"IBM Plex Sans Arabic"', 'system-ui', 'Segoe UI', 'Tahoma', 'sans-serif'],
        arabic: ['"IBM Plex Sans Arabic"', 'Inter', 'system-ui', 'Tahoma', 'sans-serif'],
      },
      boxShadow: {
        soft: '0 1px 2px rgba(9, 15, 29, 0.04)',
        lift: '0 2px 4px rgba(9, 15, 29, 0.06), 0 24px 48px -24px rgba(9, 15, 29, 0.35)',
      },
    },
  },
  plugins: [],
}

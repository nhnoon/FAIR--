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
        sidebar: { DEFAULT: token('sidebar'), fg: token('sidebar-fg'), muted: token('sidebar-muted'), active: token('sidebar-active') },
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
        soft: '0 1px 2px rgba(8, 15, 30, 0.05), 0 4px 16px -8px rgba(8, 15, 30, 0.10)',
        lift: '0 2px 4px rgba(8, 15, 30, 0.06), 0 18px 40px -20px rgba(8, 15, 30, 0.40)',
      },
    },
  },
  plugins: [],
}

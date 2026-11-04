// Saved examples: recorded Muse Spark outputs for synthetic offers, written by backend/scripts/build_examples.py.
// They are always labelled as saved. Nothing here is a live analysis.
import file from './saved_examples.json'

export const SAVED_EXAMPLES = file.cases

const TITLES = {
  'FAIR-011': { en: 'Cancelling after a free trial', ar: 'الإلغاء بعد انتهاء التجربة' },
  'FAIR-012': { en: 'A price that “never changes”', ar: 'سعر «لن يتغيّر أبدًا»' },
  'FAIR-026': { en: 'The same trial, in Arabic', ar: 'تجربة مجانية بالعربية' },
}

export const exampleTitle = (id, lang) => TITLES[id]?.[lang] ?? id
export const findExample = (id) => SAVED_EXAMPLES.find((ex) => ex.id === id)

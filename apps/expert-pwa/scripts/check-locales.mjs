// Verifies that every locale defines the same message keys (CLAUDE.md §7).
// Plural variants are compared by base key, and each locale must define every
// plural category its language requires (e.g. Ukrainian: one/few/many/other).
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const LOCALES_DIR = fileURLToPath(new URL('../src/locales/', import.meta.url));
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;

function flatten(object, prefix = '') {
  return Object.entries(object).flatMap(([key, value]) =>
    typeof value === 'object' && value !== null
      ? flatten(value, `${prefix}${key}.`)
      : [[`${prefix}${key}`, value]],
  );
}

const locales = readdirSync(LOCALES_DIR);
const problems = [];
const baseKeysByLocale = new Map();

for (const locale of locales) {
  const dir = join(LOCALES_DIR, locale);
  const entries = readdirSync(dir).flatMap((file) =>
    flatten(JSON.parse(readFileSync(join(dir, file), 'utf8')), `${file.replace('.json', '')}:`),
  );
  const required = new Intl.PluralRules(locale).resolvedOptions().pluralCategories;
  const plurals = new Map();
  for (const [key, value] of entries) {
    if (typeof value !== 'string' || value.trim() === '') problems.push(`${locale}: empty ${key}`);
    const match = key.match(PLURAL_SUFFIX);
    if (match) {
      const base = key.replace(PLURAL_SUFFIX, '');
      plurals.set(base, [...(plurals.get(base) ?? []), match[1]]);
    }
  }
  for (const [base, categories] of plurals) {
    for (const category of required) {
      if (!categories.includes(category)) problems.push(`${locale}: ${base} missing _${category}`);
    }
  }
  baseKeysByLocale.set(locale, new Set(entries.map(([key]) => key.replace(PLURAL_SUFFIX, ''))));
}

const [reference, ...others] = locales;
for (const locale of others) {
  const a = baseKeysByLocale.get(reference);
  const b = baseKeysByLocale.get(locale);
  for (const key of a) if (!b.has(key)) problems.push(`${locale}: missing ${key}`);
  for (const key of b) if (!a.has(key)) problems.push(`${reference}: missing ${key}`);
}

if (problems.length > 0) {
  console.error(`Locale check failed:\n  ${problems.join('\n  ')}`);
  process.exit(1);
}
console.log(`Locale check passed for: ${locales.join(', ')}`);

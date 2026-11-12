import i18next, { type i18n } from 'i18next';
import { initReactI18next } from 'react-i18next';

import type { Locale as ApiLocale } from '@upcycling/api-client';

import en from '../../locales/en/common.json';
import uk from '../../locales/uk/common.json';
import type { PreferenceStore } from '../platform/preferenceStore';

export const SUPPORTED_LOCALES = ['uk', 'en'] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];
export const DEFAULT_LOCALE: AppLocale = 'uk';

// Compile-time guard: the UI locales must match the API's `Locale` enum exactly.
type Same<A, B> = [A] extends [B] ? ([B] extends [A] ? true : false) : false;
const localesMatchApi: Same<AppLocale, ApiLocale> = true;
void localesMatchApi;

export const resources = { uk: { common: uk }, en: { common: en } } as const;

const LOCALE_KEY = 'locale';

export function isSupportedLocale(value: unknown): value is AppLocale {
  return typeof value === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/**
 * Resolution order before sign-in: locally stored choice, then the default (`uk`).
 * After sign-in the server-side `preferred_locale` wins (see `useLocaleSync`).
 */
export async function createI18n(store: PreferenceStore): Promise<i18n> {
  const stored = store.get(LOCALE_KEY);
  const instance = i18next.createInstance();
  instance.on('languageChanged', (language) => {
    if (typeof document !== 'undefined') document.documentElement.lang = language;
    if (isSupportedLocale(language)) store.set(LOCALE_KEY, language);
  });
  await instance.use(initReactI18next).init({
    resources,
    lng: isSupportedLocale(stored) ? stored : DEFAULT_LOCALE,
    fallbackLng: DEFAULT_LOCALE,
    supportedLngs: SUPPORTED_LOCALES,
    defaultNS: 'common',
    ns: ['common'],
    interpolation: { escapeValue: false }, // React already escapes output.
    returnNull: false,
  });
  return instance;
}

export function currentLocale(instance: i18n): AppLocale {
  return isSupportedLocale(instance.language) ? instance.language : DEFAULT_LOCALE;
}

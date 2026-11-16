import { describe, expect, it } from 'vitest';

import { DEFAULT_LOCALE, createI18n, isSupportedLocale } from '../../src/shared/i18n';
import { createMemoryPreferenceStore } from '../../src/shared/platform/preferenceStore';

describe('i18n', () => {
  it('defaults to Ukrainian when no preference is stored', async () => {
    const i18n = await createI18n(createMemoryPreferenceStore());
    expect(DEFAULT_LOCALE).toBe('uk');
    expect(i18n.language).toBe('uk');
    expect(i18n.t('login.title')).toBe('Вхід');
  });

  it('uses a stored supported locale and ignores unsupported ones', async () => {
    const en = await createI18n(createMemoryPreferenceStore({ locale: 'en' }));
    expect(en.language).toBe('en');
    const unsupported = await createI18n(createMemoryPreferenceStore({ locale: 'de' }));
    expect(unsupported.language).toBe('uk');
  });

  it('persists language changes and updates <html lang>', async () => {
    const store = createMemoryPreferenceStore();
    const i18n = await createI18n(store);
    await i18n.changeLanguage('en');
    expect(store.get('locale')).toBe('en');
    expect(document.documentElement.lang).toBe('en');
  });

  it('applies Ukrainian plural categories', async () => {
    const i18n = await createI18n(createMemoryPreferenceStore());
    const text = (count: number) => i18n.t('login.codeValidity', { count });
    expect(text(1)).toContain('1 хвилину');
    expect(text(3)).toContain('3 хвилини');
    expect(text(5)).toContain('5 хвилин');
    expect(text(21)).toContain('21 хвилину');
    expect(text(15)).toContain('15 хвилин');
  });

  it('applies English plural categories', async () => {
    const i18n = await createI18n(createMemoryPreferenceStore({ locale: 'en' }));
    expect(i18n.t('login.codeValidity', { count: 1 })).toContain('1 minute.');
    expect(i18n.t('login.codeValidity', { count: 15 })).toContain('15 minutes.');
  });

  it('recognises only uk and en', () => {
    expect(isSupportedLocale('uk')).toBe(true);
    expect(isSupportedLocale('en')).toBe(true);
    expect(isSupportedLocale('ru')).toBe(false);
    expect(isSupportedLocale(undefined)).toBe(false);
  });
});

import { useTranslation } from 'react-i18next';

import type { MediaCategory } from '@upcycling/api-client';

import { MEDIA_CATEGORIES } from './categories';

/**
 * One-tap photo category picker (radio buttons styled as chips). Used while capturing (the
 * choice applies to the next photos) and on the photo screen (re-categorize one photo).
 * Categories are first, "No category" last: it is the exception, not the default.
 */
export function CategoryChips({
  name,
  legend,
  hideLegend = false,
  scroll = false,
  value,
  onChange,
  disabled,
}: {
  name: string;
  legend: string;
  hideLegend?: boolean;
  /** One horizontally scrolling row instead of wrapping (saves vertical space). */
  scroll?: boolean;
  value: MediaCategory | null;
  onChange: (category: MediaCategory | null) => void;
  disabled?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <fieldset className={scroll ? 'chips chips--scroll' : 'chips'} disabled={disabled}>
      <legend className={hideLegend ? 'visually-hidden' : undefined}>{legend}</legend>
      {[...MEDIA_CATEGORIES, null].map((category) => (
        <label key={category ?? 'none'} className="chip">
          <input
            type="radio"
            name={name}
            checked={value === category}
            onChange={() => onChange(category)}
          />
          <span>{category ? t(`categories.${category}`) : t('photo.noCategory')}</span>
        </label>
      ))}
    </fieldset>
  );
}

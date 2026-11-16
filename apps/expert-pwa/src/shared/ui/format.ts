/** Locale-aware formatting helpers (no hardcoded units or date formats in components). */

export function formatDate(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(new Date(iso));
}

export function formatDateTime(iso: string, locale: string): string {
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(iso),
  );
}

export function formatBytes(bytes: number, locale: string): string {
  const [value, unit] =
    bytes >= 1024 * 1024 ? [bytes / (1024 * 1024), 'megabyte'] : [bytes / 1024, 'kilobyte'];
  return new Intl.NumberFormat(locale, {
    style: 'unit',
    unit,
    maximumFractionDigits: 1,
  }).format(value);
}

/** "image/heic" -> "HEIC" */
export function formatLabel(contentType: string): string {
  return (contentType.split('/')[1] ?? contentType).toUpperCase();
}

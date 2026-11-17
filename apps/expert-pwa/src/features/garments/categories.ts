import type { MediaCategory } from '@upcycling/api-client';

/** Display order of photo categories (values are the stable API codes). */
export const MEDIA_CATEGORIES = [
  'front',
  'back',
  'detail',
  'fabric',
  'defect',
  'label',
] as const satisfies readonly MediaCategory[];

// Compile-time guard: every API category is displayed.
type Missing = Exclude<MediaCategory, (typeof MEDIA_CATEGORIES)[number]>;
const allCategoriesShown: [Missing] extends [never] ? true : false = true;
void allCategoriesShown;

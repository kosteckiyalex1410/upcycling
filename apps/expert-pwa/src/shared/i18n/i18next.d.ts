import 'i18next';

import type uk from '../../locales/uk/common.json';

// Typed translation keys: a missing or misspelt key fails `tsc`.
// `uk` is the reference locale; `pnpm check:locales` enforces parity with `en`.
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common';
    resources: { common: typeof uk };
  }
}

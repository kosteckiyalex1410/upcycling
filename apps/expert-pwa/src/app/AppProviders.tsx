import { QueryClientProvider, type QueryClient } from '@tanstack/react-query';
import type { i18n } from 'i18next';
import type { ReactNode } from 'react';
import { I18nextProvider } from 'react-i18next';

import type { ApiClient } from '@upcycling/api-client';

import { ApiProvider } from '../shared/api/ApiProvider';

export type AppServices = { api: ApiClient; queryClient: QueryClient; i18n: i18n };

/** Composition root for app-wide services; tests pass their own instances. */
export function AppProviders({
  services,
  children,
}: {
  services: AppServices;
  children: ReactNode;
}) {
  return (
    <I18nextProvider i18n={services.i18n}>
      <QueryClientProvider client={services.queryClient}>
        <ApiProvider client={services.api}>{children}</ApiProvider>
      </QueryClientProvider>
    </I18nextProvider>
  );
}

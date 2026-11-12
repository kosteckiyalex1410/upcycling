import type { ReactNode } from 'react';

import type { ApiClient } from '@upcycling/api-client';

import { ApiContext } from './apiContext';

export function ApiProvider({ client, children }: { client: ApiClient; children: ReactNode }) {
  return <ApiContext value={client}>{children}</ApiContext>;
}

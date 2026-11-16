import { QueryClient } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';

import { AppProviders } from './app/AppProviders';
import { routes } from './app/routes';
import { UpdatePrompt } from './app/UpdatePrompt';
import { createAppApiClient } from './shared/api/client';
import { createI18n } from './shared/i18n';
import { createBrowserPreferenceStore } from './shared/platform/preferenceStore';
import './styles.css';

async function bootstrap() {
  const i18n = await createI18n(createBrowserPreferenceStore());
  const services = {
    i18n,
    api: createAppApiClient(() => i18n.language),
    queryClient: new QueryClient({
      defaultOptions: { queries: { refetchOnWindowFocus: true, retry: 1 } },
    }),
  };
  const router = createBrowserRouter(routes);

  const root = document.getElementById('root');
  if (!root) throw new Error('Missing #root element');
  createRoot(root).render(
    <StrictMode>
      <AppProviders services={services}>
        <UpdatePrompt />
        <RouterProvider router={router} />
      </AppProviders>
    </StrictMode>,
  );
}

void bootstrap();

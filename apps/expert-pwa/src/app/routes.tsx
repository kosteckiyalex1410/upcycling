import type { RouteObject } from 'react-router';

import { LoginPage } from '../features/auth/LoginPage';
import { RequireAuth } from '../features/auth/RequireAuth';
import { VerifyLinkPage } from '../features/auth/VerifyLinkPage';
import { GarmentListPage } from '../features/garments/GarmentListPage';
import { GarmentPage } from '../features/garments/GarmentPage';
import { PhotoPage } from '../features/garments/PhotoPage';
import { SettingsPage } from '../features/settings/SettingsPage';
import { AppLayout } from './AppLayout';
import { NotFoundPage } from './NotFoundPage';

export const routes: RouteObject[] = [
  { path: '/login', element: <LoginPage /> },
  { path: '/auth/verify', element: <VerifyLinkPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { index: true, element: <GarmentListPage /> },
          { path: 'garments/:garmentId', element: <GarmentPage /> },
          { path: 'garments/:garmentId/photos/:mediaId', element: <PhotoPage /> },
          { path: 'settings', element: <SettingsPage /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFoundPage /> },
];

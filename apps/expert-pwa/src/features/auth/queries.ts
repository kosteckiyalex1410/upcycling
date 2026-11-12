import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { Locale, Me } from '@upcycling/api-client';

import { useApi } from '../../shared/api/apiContext';
import { unwrap } from '../../shared/api/client';
import { ApiError } from '../../shared/api/errors';

export const meQueryKey = ['me'] as const;

/** Current user, or `null` when not signed in. */
export function useMe() {
  const api = useApi();
  return useQuery({
    queryKey: meQueryKey,
    queryFn: async (): Promise<Me | null> => {
      try {
        return await unwrap(api.GET('/api/v1/me'));
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    // Retry transient failures (network, 5xx) but never client errors such as 401.
    retry: (failureCount, error) =>
      failureCount < 2 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
  });
}

export function useRequestLogin() {
  const api = useApi();
  return useMutation({
    mutationFn: (email: string) =>
      unwrap(api.POST('/api/v1/auth/login-requests', { body: { email } })),
  });
}

export function useVerifyToken() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (token: string) =>
      unwrap(api.POST('/api/v1/auth/login-requests/verify-token', { body: { token } })),
    onSuccess: (me) => queryClient.setQueryData(meQueryKey, me),
  });
}

export function useVerifyCode() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ challengeId, code }: { challengeId: string; code: string }) =>
      unwrap(
        api.POST('/api/v1/auth/login-requests/{challenge_id}/verify-code', {
          params: { path: { challenge_id: challengeId } },
          body: { code },
        }),
      ),
    onSuccess: (me) => queryClient.setQueryData(meQueryKey, me),
  });
}

export function useLogout({ everywhere = false } = {}) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(
        everywhere ? api.POST('/api/v1/auth/sessions/revoke-all') : api.POST('/api/v1/auth/logout'),
      ),
    onSuccess: () => {
      queryClient.clear();
      queryClient.setQueryData(meQueryKey, null);
    },
  });
}

export function useUpdatePreferredLocale() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (preferredLocale: Locale) =>
      unwrap(api.PATCH('/api/v1/me', { body: { preferred_locale: preferredLocale } })),
    onSuccess: (me) => queryClient.setQueryData(meQueryKey, me),
  });
}

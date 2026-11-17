import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';

import type { Garment, MediaCategory } from '@upcycling/api-client';

import { useApi } from '../../shared/api/apiContext';
import { unwrap } from '../../shared/api/client';

// Separate roots: invalidating the list must not refetch every open garment.
export const garmentsKey = ['garments'] as const;
export const garmentKey = (id: string) => ['garment', id] as const;

export function invalidateGarment(queryClient: QueryClient, id: string) {
  void queryClient.invalidateQueries({ queryKey: garmentsKey });
  void queryClient.invalidateQueries({ queryKey: garmentKey(id) });
}

export function useGarments() {
  const api = useApi();
  return useInfiniteQuery({
    queryKey: garmentsKey,
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET('/api/v1/garments', { params: { query: { cursor: pageParam } } })),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
}

export function useGarment(id: string) {
  const api = useApi();
  return useQuery({
    queryKey: garmentKey(id),
    queryFn: () =>
      unwrap(api.GET('/api/v1/garments/{garment_id}', { params: { path: { garment_id: id } } })),
  });
}

export function useCreateGarment() {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    // One idempotency key per tap: an automatic retry cannot create a duplicate.
    mutationFn: (clientRequestId: string) =>
      unwrap(api.POST('/api/v1/garments', { body: { client_request_id: clientRequestId } })),
    retry: 2,
    onSuccess: (garment) => {
      queryClient.setQueryData(garmentKey(garment.id), garment);
      void queryClient.invalidateQueries({ queryKey: garmentsKey });
    },
  });
}

export function useUpdateGarment(id: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (changes: { title?: string | null; notes?: string | null }) =>
      unwrap(
        api.PATCH('/api/v1/garments/{garment_id}', {
          params: { path: { garment_id: id } },
          body: changes,
        }),
      ),
    onSuccess: (garment: Garment) => {
      queryClient.setQueryData(garmentKey(id), garment);
      void queryClient.invalidateQueries({ queryKey: garmentsKey });
    },
  });
}

export function useDeleteGarment(id: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      unwrap(api.DELETE('/api/v1/garments/{garment_id}', { params: { path: { garment_id: id } } })),
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: garmentKey(id) });
      void queryClient.invalidateQueries({ queryKey: garmentsKey });
    },
  });
}

export function useUpdateMediaCategory(garmentId: string, mediaId: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (category: MediaCategory | null) =>
      unwrap(
        api.PATCH('/api/v1/media/{media_id}', {
          params: { path: { media_id: mediaId } },
          body: { category },
        }),
      ),
    onSuccess: (media) => {
      queryClient.setQueryData<Garment>(garmentKey(garmentId), (garment) =>
        garment
          ? { ...garment, media: garment.media.map((m) => (m.id === media.id ? media : m)) }
          : garment,
      );
      invalidateGarment(queryClient, garmentId);
    },
  });
}

export function useDeleteMedia(garmentId: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mediaId: string) =>
      unwrap(api.DELETE('/api/v1/media/{media_id}', { params: { path: { media_id: mediaId } } })),
    onSuccess: () => invalidateGarment(queryClient, garmentId),
  });
}

export function useDeleteVoiceNote(garmentId: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (voiceNoteId: string) =>
      unwrap(
        api.DELETE('/api/v1/voice-notes/{voice_note_id}', {
          params: { path: { voice_note_id: voiceNoteId } },
        }),
      ),
    onSuccess: () => invalidateGarment(queryClient, garmentId),
  });
}

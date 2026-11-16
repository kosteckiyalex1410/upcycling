import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState, useSyncExternalStore } from 'react';

import type { Garment } from '@upcycling/api-client';

import { useApi } from '../../shared/api/apiContext';
import { unwrap } from '../../shared/api/client';
import { declaredContentType, sha256Hex, xhrUploadTransport } from '../../shared/platform/photos';
import { garmentKey, invalidateGarment } from './queries';
import { UploadQueue } from './uploadQueue';

/** Upload queue bound to one garment; stops (and leaves pending photos) on unmount. */
export function useUploadQueue(garmentId: string) {
  const api = useApi();
  const queryClient = useQueryClient();
  const [queue] = useState(
    () =>
      new UploadQueue({
        requestUpload: (body) =>
          unwrap(
            api.POST('/api/v1/garments/{garment_id}/media/uploads', {
              params: { path: { garment_id: garmentId } },
              body,
            }),
          ),
        complete: (mediaId) =>
          unwrap(
            api.POST('/api/v1/garments/{garment_id}/media/complete', {
              params: { path: { garment_id: garmentId } },
              body: { media_id: mediaId },
            }),
          ),
        transport: xhrUploadTransport,
        hash: sha256Hex,
        contentType: declaredContentType,
        onFinished: (media) => {
          // Show the result at once (no gap between the upload tile and the photo), then
          // reconcile with the server.
          queryClient.setQueryData<Garment>(garmentKey(garmentId), (garment) =>
            garment
              ? { ...garment, media: [...garment.media.filter((m) => m.id !== media.id), media] }
              : garment,
          );
          invalidateGarment(queryClient, garmentId);
        },
      }),
  );
  useEffect(() => {
    queue.activate();
    return () => queue.dispose();
  }, [queue]);
  const items = useSyncExternalStore(queue.subscribe, queue.getSnapshot);
  return { queue, items, active: items.some((item) => item.phase !== 'failed') };
}

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { Garment, MediaAsset, VoiceNote } from '@upcycling/api-client';

import { voicePlatform } from '../../src/features/garments/useVoiceNotes';
import type { MicrophoneEnv, RecorderLike } from '../../src/shared/platform/audioRecorder';
import { memoryVoiceDraftStore, type VoiceDraftStore } from '../../src/shared/platform/voiceDrafts';
import { EXPERT, json, mockApi, renderApp } from './harness';

const G = '0193aaaa-0000-7000-8000-000000000001';
const M = '0193bbbb-0000-7000-8000-000000000002';
const R = '0193bbbb-0000-7000-8000-000000000003';
const U = '0193bbbb-0000-7000-8000-000000000004';
const V = '0193cccc-0000-7000-8000-000000000005';

const readyPhoto: MediaAsset = {
  id: M,
  garment_id: G,
  category: 'front',
  status: 'ready',
  error_code: null,
  original_filename: 'IMG_0001.HEIC',
  content_type: 'image/heic',
  size_bytes: 2_621_440,
  sha256: 'a'.repeat(64),
  width: 3024,
  height: 4032,
  created_at: '2026-11-16T10:00:00Z',
  completed_at: '2026-11-16T10:00:05Z',
  thumbnail_url: `/api/v1/media/${M}/thumbnail`,
  preview_url: `/api/v1/media/${M}/preview`,
  original_url: `/api/v1/media/${M}/original`,
};

const rejectedPhoto: MediaAsset = {
  ...readyPhoto,
  id: R,
  category: 'defect',
  status: 'rejected',
  error_code: 'invalid_image',
  content_type: null,
  thumbnail_url: null,
  preview_url: null,
  original_url: null,
};

const uncategorized: MediaAsset = {
  ...readyPhoto,
  id: U,
  category: null,
  thumbnail_url: `/api/v1/media/${U}/thumbnail`,
};

const voiceNote: VoiceNote = {
  id: V,
  garment_id: G,
  status: 'ready',
  error_code: null,
  content_type: 'audio/mp4',
  codec: 'aac',
  size_bytes: 120_000,
  sha256: 'b'.repeat(64),
  duration_ms: 42_000,
  recorded_at: '2026-11-16T10:00:00Z',
  created_at: '2026-11-16T10:00:00Z',
  completed_at: '2026-11-16T10:00:02Z',
  audio_url: `/api/v1/voice-notes/${V}/audio`,
};

const garment = (patch: Partial<Garment> = {}): Garment => ({
  id: G,
  title: 'Джинсова куртка',
  notes: null,
  created_at: '2026-11-16T09:00:00Z',
  updated_at: '2026-11-16T09:00:00Z',
  media: [readyPhoto, rejectedPhoto],
  voice_notes: [],
  ...patch,
});

/** A microphone that "records" until stopped (stands in for getUserMedia + MediaRecorder). */
function fakeMicrophone(patch: Partial<MicrophoneEnv> = {}): MicrophoneEnv {
  const track = { stop: vi.fn(), addEventListener: vi.fn() };
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] };
  return {
    secure: true,
    getUserMedia: () => Promise.resolve(stream as unknown as MediaStream),
    isTypeSupported: (type) => type.startsWith('audio/mp4'),
    createRecorder: () => {
      const recorder: RecorderLike = {
        mimeType: 'audio/mp4; codecs=mp4a.40.2',
        state: 'inactive',
        start() {
          (this as { state: string }).state = 'recording';
        },
        stop() {
          (this as { state: string }).state = 'inactive';
          this.ondataavailable?.({ data: new Blob(['fake-aac']) });
          this.onstop?.();
        },
        ondataavailable: null,
        onstop: null,
        onerror: null,
      };
      return recorder;
    },
    ...patch,
  };
}

function usePlatform(microphone: MicrophoneEnv, drafts: VoiceDraftStore = memoryVoiceDraftStore()) {
  vi.spyOn(voicePlatform, 'microphone').mockReturnValue(microphone);
  vi.spyOn(voicePlatform, 'drafts').mockReturnValue(drafts);
}

afterEach(() => vi.restoreAllMocks());

const me = () => json(200, EXPERT);

describe('garment list', () => {
  it('lists projects with photo counts and creates a new one', async () => {
    const calls = mockApi({
      'GET /api/v1/me': me,
      'GET /api/v1/garments': () =>
        json(200, {
          items: [
            {
              id: G,
              title: null,
              created_at: '2026-11-16T09:00:00Z',
              updated_at: '2026-11-16T09:00:00Z',
              photo_count: 3,
              cover_thumbnail_url: `/api/v1/media/${M}/thumbnail`,
            },
          ],
          next_cursor: null,
        }),
      'POST /api/v1/garments': () => json(201, garment({ title: null, media: [] })),
      [`GET /api/v1/garments/${G}`]: () => json(200, garment({ title: null, media: [] })),
    });
    const user = userEvent.setup();
    const { router } = await renderApp('/');

    const card = await screen.findByRole('link', { name: /Проєкт без назви/ });
    expect(within(card).getByText(/3 фото/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Новий проєкт' }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/garments/${G}`));
    const create = calls.find((c) => c.method === 'POST' && c.path === '/api/v1/garments');
    const body = create?.body as { client_request_id: string };
    expect(body.client_request_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('shows an empty state', async () => {
    mockApi({
      'GET /api/v1/me': me,
      'GET /api/v1/garments': () => json(200, { items: [], next_cursor: null }),
    });
    await renderApp('/');
    expect(await screen.findByText(/Ще немає проєктів/)).toBeInTheDocument();
  });
});

describe('garment page', () => {
  it('shows all photos in one gallery with category labels and capture actions', async () => {
    usePlatform(fakeMicrophone());
    const calls = mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () =>
        json(200, garment({ media: [readyPhoto, uncategorized, rejectedPhoto] })),
      [`DELETE /api/v1/media/${R}`]: () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    await renderApp(`/garments/${G}`);

    expect(await screen.findByRole('heading', { name: 'Джинсова куртка' })).toBeInTheDocument();
    const gallery = screen.getByRole('region', { name: /Фото/ });
    expect(within(gallery).getByRole('link', { name: 'Відкрити фото 1: Перед' })).toHaveAttribute(
      'href',
      `/garments/${G}/photos/${M}`,
    );
    expect(within(gallery).getAllByText('Перед')[0]).toBeInTheDocument(); // label on the thumbnail
    expect(within(gallery).getByRole('link', { name: 'Відкрити фото 2' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Спинка' })).not.toBeInTheDocument();

    for (const name of ['Зробити фото', 'Вибрати фото', 'Записати голос']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument();
    }
    const chips = screen.getByRole('group', { name: 'Категорія наступних фото' });
    expect(within(chips).getByRole('radio', { name: 'Перед' })).toBeChecked();
    expect(screen.queryByText(/Створено/)).not.toBeInTheDocument(); // no redundant text

    expect(within(gallery).getByText('Відхилено')).toBeInTheDocument();
    expect(within(gallery).getByText('Файл пошкоджений або не є зображенням.')).toBeInTheDocument();
    await user.click(within(gallery).getByRole('button', { name: 'Прибрати' }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'DELETE' && c.path.endsWith(R))).toBe(true),
    );
  });

  it('gives new photos the selected category until it is changed', async () => {
    usePlatform(fakeMicrophone());
    const calls = mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () => json(200, garment({ media: [] })),
      [`POST /api/v1/garments/${G}/media/uploads`]: () =>
        json(200, { media: { ...uncategorized, status: 'ready' }, upload: null }),
    });
    const user = userEvent.setup();
    const { container } = await renderApp(`/garments/${G}`);
    await screen.findByRole('heading', { name: 'Джинсова куртка' });

    const library = container.querySelector<HTMLInputElement>('input[type="file"][multiple]')!;
    const chips = screen.getByRole('group', { name: 'Категорія наступних фото' });
    const uploads = () => calls.filter((c) => c.path.endsWith('/media/uploads'));

    await user.upload(library, [
      new File(['a'], 'IMG_1.HEIC', { type: 'image/heic' }),
      new File(['b'], 'IMG_2.JPG', { type: 'image/jpeg' }),
    ]);
    await waitFor(() => expect(uploads()).toHaveLength(2));
    await user.click(within(chips).getByRole('radio', { name: 'Дефекти' }));
    await user.upload(library, new File(['c'], 'IMG_3.JPG', { type: 'image/jpeg' }));
    await waitFor(() => expect(uploads()).toHaveLength(3));
    await user.click(within(chips).getByRole('radio', { name: 'Без категорії' }));
    await user.upload(library, new File(['d'], 'IMG_4.JPG', { type: 'image/jpeg' }));
    await waitFor(() => expect(uploads()).toHaveLength(4));

    expect(uploads().map((c) => (c.body as { category: string | null }).category)).toEqual([
      'front',
      'front',
      'defect',
      null,
    ]);
  });

  it('renames the project in place and saves a text note', async () => {
    usePlatform(fakeMicrophone());
    const calls = mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () => json(200, garment({ media: [] })),
      [`PATCH /api/v1/garments/${G}`]: (_, body) =>
        json(200, garment({ media: [], ...(body as Partial<Garment>) })),
    });
    const user = userEvent.setup();
    await renderApp(`/garments/${G}`);

    await user.click(await screen.findByRole('button', { name: 'Перейменувати' }));
    const name = screen.getByLabelText('Назва');
    expect(name).toHaveFocus();
    await user.clear(name);
    await user.type(name, '  Вовняний блейзер {Enter}');
    expect(await screen.findByRole('heading', { name: 'Вовняний блейзер' })).toBeInTheDocument();

    await user.click(screen.getByText('Текстова нотатка', { selector: 'summary' })); // collapsed
    await user.type(screen.getByRole('textbox', { name: 'Текстова нотатка' }), ' Потертості ');
    await user.click(screen.getByRole('button', { name: 'Зберегти' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Збережено');
    expect(calls.filter((c) => c.method === 'PATCH').map((c) => c.body)).toEqual([
      { title: 'Вовняний блейзер' },
      { notes: 'Потертості' },
    ]);
  });

  it('asks for confirmation before deleting the project', async () => {
    usePlatform(fakeMicrophone());
    const calls = mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () => json(200, garment({ media: [] })),
      [`DELETE /api/v1/garments/${G}`]: () => new Response(null, { status: 204 }),
      'GET /api/v1/garments': () => json(200, { items: [], next_cursor: null }),
    });
    const user = userEvent.setup();
    const { router } = await renderApp(`/garments/${G}`);

    await user.click(await screen.findByRole('button', { name: 'Інші дії' }));
    await user.click(screen.getByRole('button', { name: 'Видалити проєкт' }));
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Видалити остаточно' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
    expect(calls.some((c) => c.method === 'DELETE' && c.path.endsWith(G))).toBe(true);
  });
});

describe('photo page', () => {
  it('shows details, changes the category and deletes after confirmation', async () => {
    let current = readyPhoto;
    const calls = mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () => json(200, garment({ media: [current] })),
      [`PATCH /api/v1/media/${M}`]: (_, body) => {
        current = { ...current, ...(body as Partial<MediaAsset>) };
        return json(200, current);
      },
      [`DELETE /api/v1/media/${M}`]: () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    const { router } = await renderApp(`/garments/${G}/photos/${M}`);

    expect(await screen.findByRole('img', { name: 'Фото: Перед' })).toHaveAttribute(
      'src',
      `/api/v1/media/${M}/preview`,
    );
    expect(screen.getByText('HEIC')).toBeInTheDocument();
    expect(screen.getByText('3024 × 4032 пікс.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Завантажити оригінал' })).toHaveAttribute(
      'href',
      `/api/v1/media/${M}/original`,
    );

    const chips = screen.getByRole('group', { name: 'Категорія' });
    expect(within(chips).getByRole('radio', { name: 'Перед' })).toBeChecked();
    await user.click(within(chips).getByRole('radio', { name: 'Етикетка' }));
    expect(await screen.findByRole('heading', { name: 'Етикетка' })).toBeInTheDocument();
    await user.click(within(chips).getByRole('radio', { name: 'Без категорії' }));
    expect(await screen.findByRole('heading', { name: 'Фото' })).toBeInTheDocument();
    expect(calls.filter((c) => c.method === 'PATCH').map((c) => c.body)).toEqual([
      { category: 'label' },
      { category: null },
    ]);

    await user.click(screen.getByRole('button', { name: 'Видалити фото' }));
    await user.click(screen.getByRole('button', { name: 'Видалити остаточно' }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/garments/${G}`));
  });
});

describe('voice notes', () => {
  it('records, reviews and saves a voice note with its real format', async () => {
    usePlatform(fakeMicrophone());
    let saved: VoiceNote[] = [];
    const calls = mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () => json(200, garment({ media: [], voice_notes: saved })),
      [`POST /api/v1/garments/${G}/voice-notes/uploads`]: () => {
        saved = [voiceNote];
        return json(200, { voice_note: voiceNote, upload: null });
      },
    });
    const user = userEvent.setup();
    await renderApp(`/garments/${G}`);

    expect(await screen.findByText('Ще немає голосових нотаток.')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Записати голос' }));
    expect(await screen.findByText('Запис')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Зупинити' }));

    expect(await screen.findByText(/Новий запис ·/)).toBeInTheDocument();
    expect(screen.getByLabelText('Прослухати новий запис')).toHaveAttribute('src');
    await user.click(screen.getByRole('button', { name: 'Зберегти запис' }));

    await waitFor(() =>
      expect(calls.some((c) => c.path.endsWith('/voice-notes/uploads'))).toBe(true),
    );
    const body = calls.find((c) => c.path.endsWith('/voice-notes/uploads'))?.body;
    expect(body).toMatchObject({
      content_type: 'audio/mp4; codecs=mp4a.40.2',
      size_bytes: 8,
      duration_ms: expect.any(Number) as number,
      recorded_at: expect.any(String) as string,
    });
    expect(await screen.findByRole('article', { name: 'Нотатка 1' })).toBeInTheDocument();
    // Back to the capture buttons.
    expect(screen.getByRole('button', { name: 'Записати голос' })).toBeInTheDocument();
  });

  it('explains a denied microphone permission', async () => {
    const denied = Object.assign(new Error('denied'), { name: 'NotAllowedError' });
    usePlatform(fakeMicrophone({ getUserMedia: () => Promise.reject(denied) }));
    mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () => json(200, garment({ media: [] })),
    });
    const user = userEvent.setup();
    await renderApp(`/garments/${G}`);
    await user.click(await screen.findByRole('button', { name: 'Записати голос' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Немає доступу до мікрофона');
    await user.click(screen.getByRole('button', { name: 'Закрити' }));
    expect(screen.getByRole('button', { name: 'Записати голос' })).toBeInTheDocument();
  });

  it('explains that recording needs HTTPS', async () => {
    usePlatform(fakeMicrophone({ secure: false }));
    mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () => json(200, garment({ media: [] })),
    });
    const user = userEvent.setup();
    await renderApp(`/garments/${G}`);
    await user.click(await screen.findByRole('button', { name: 'Записати голос' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTPS');
    expect(screen.queryByRole('button', { name: 'Спробувати знову' })).not.toBeInTheDocument();
  });

  it('brings back a recording that was not saved before the app closed', async () => {
    const drafts = memoryVoiceDraftStore([
      {
        clientUploadId: 'draft-1',
        garmentId: G,
        data: new TextEncoder().encode('fake-aac').buffer,
        mimeType: 'audio/mp4',
        durationMs: 61_000,
        recordedAt: '2026-11-16T10:00:00Z',
      },
    ]);
    usePlatform(fakeMicrophone(), drafts);
    const calls = mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () => json(200, garment({ media: [] })),
      [`POST /api/v1/garments/${G}/voice-notes/uploads`]: () =>
        json(200, { voice_note: voiceNote, upload: null }),
    });
    const user = userEvent.setup();
    await renderApp(`/garments/${G}`);

    expect(await screen.findByText('Новий запис 1:01 · Не збережено')).toBeInTheDocument();
    expect(calls.some((c) => c.path.endsWith('/voice-notes/uploads'))).toBe(false);
    await user.click(screen.getByRole('button', { name: 'Зберегти запис' }));
    await waitFor(() => {
      const call = calls.find((c) => c.path.endsWith('/voice-notes/uploads'));
      expect(call?.body).toMatchObject({ client_upload_id: 'draft-1' });
    });
    await waitFor(async () => expect(await drafts.list(G)).toEqual([]));
  });

  it('plays saved notes from the authenticated endpoint and deletes after confirmation', async () => {
    usePlatform(fakeMicrophone());
    const calls = mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () =>
        json(200, garment({ media: [], voice_notes: [voiceNote] })),
      [`DELETE /api/v1/voice-notes/${V}`]: () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    await renderApp(`/garments/${G}`);

    const note = await screen.findByRole('article', { name: 'Нотатка 1' });
    expect(within(note).getByText(/0:42/)).toBeInTheDocument();
    expect(within(note).getByLabelText('Відтворити: Нотатка 1')).toHaveAttribute(
      'src',
      `/api/v1/voice-notes/${V}/audio`,
    );
    await user.click(within(note).getByRole('button', { name: 'Видалити нотатку' }));
    expect(calls.some((c) => c.method === 'DELETE')).toBe(false);
    await user.click(within(note).getByRole('button', { name: 'Видалити остаточно' }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'DELETE' && c.path.endsWith(V))).toBe(true),
    );
  });
});

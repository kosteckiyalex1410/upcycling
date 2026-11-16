import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import type { Garment, MediaAsset } from '@upcycling/api-client';

import { EXPERT, json, mockApi, renderApp } from './harness';

const G = '0193aaaa-0000-7000-8000-000000000001';
const M = '0193bbbb-0000-7000-8000-000000000002';
const R = '0193bbbb-0000-7000-8000-000000000003';

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

const garment = (patch: Partial<Garment> = {}): Garment => ({
  id: G,
  title: 'Джинсова куртка',
  notes: null,
  created_at: '2026-11-16T09:00:00Z',
  updated_at: '2026-11-16T09:00:00Z',
  media: [readyPhoto, rejectedPhoto],
  ...patch,
});

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
  it('groups photos by category and explains rejected uploads', async () => {
    const calls = mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () => json(200, garment()),
      [`DELETE /api/v1/media/${R}`]: () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    await renderApp(`/garments/${G}`);

    expect(await screen.findByRole('heading', { name: 'Джинсова куртка' })).toBeInTheDocument();
    for (const name of ['Перед', 'Спинка', 'Деталі', 'Тканина', 'Дефекти', 'Етикетка']) {
      expect(screen.getByRole('heading', { name })).toBeInTheDocument();
    }
    const front = screen.getByRole('region', { name: 'Перед' });
    expect(within(front).getByRole('link', { name: 'Відкрити фото: Перед' })).toHaveAttribute(
      'href',
      `/garments/${G}/photos/${M}`,
    );
    expect(within(front).getByRole('button', { name: 'Зробити фото' })).toBeInTheDocument();
    expect(within(front).getByRole('button', { name: 'Вибрати фото' })).toBeInTheDocument();

    const defects = screen.getByRole('region', { name: 'Дефекти' });
    expect(within(defects).getByText('Відхилено')).toBeInTheDocument();
    expect(within(defects).getByText('Файл пошкоджений або не є зображенням.')).toBeInTheDocument();
    await user.click(within(defects).getByRole('button', { name: 'Прибрати' }));
    await waitFor(() =>
      expect(calls.some((c) => c.method === 'DELETE' && c.path.endsWith(R))).toBe(true),
    );
  });

  it('saves the name and notes', async () => {
    const calls = mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () => json(200, garment({ media: [] })),
      [`PATCH /api/v1/garments/${G}`]: (_, body) =>
        json(200, garment({ media: [], ...(body as Partial<Garment>) })),
    });
    const user = userEvent.setup();
    await renderApp(`/garments/${G}`);

    const notes = await screen.findByLabelText('Нотатки');
    await user.type(notes, '  Потертості на манжетах ');
    await user.click(screen.getByRole('button', { name: 'Зберегти' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Збережено');
    const patch = calls.find((c) => c.method === 'PATCH');
    expect(patch?.body).toEqual({ title: 'Джинсова куртка', notes: 'Потертості на манжетах' });
  });

  it('asks for confirmation before deleting the project', async () => {
    const calls = mockApi({
      'GET /api/v1/me': me,
      [`GET /api/v1/garments/${G}`]: () => json(200, garment({ media: [] })),
      [`DELETE /api/v1/garments/${G}`]: () => new Response(null, { status: 204 }),
      'GET /api/v1/garments': () => json(200, { items: [], next_cursor: null }),
    });
    const user = userEvent.setup();
    const { router } = await renderApp(`/garments/${G}`);

    await user.click(await screen.findByRole('button', { name: 'Видалити проєкт' }));
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

    await user.selectOptions(screen.getByLabelText('Категорія'), 'label');
    expect(await screen.findByRole('heading', { name: 'Етикетка' })).toBeInTheDocument();
    expect(calls.find((c) => c.method === 'PATCH')?.body).toEqual({ category: 'label' });

    await user.click(screen.getByRole('button', { name: 'Видалити фото' }));
    await user.click(screen.getByRole('button', { name: 'Видалити остаточно' }));
    await waitFor(() => expect(router.state.location.pathname).toBe(`/garments/${G}`));
  });
});

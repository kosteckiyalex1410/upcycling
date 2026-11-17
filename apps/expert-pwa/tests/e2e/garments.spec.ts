import { fileURLToPath } from 'node:url';

import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test';

import { createExpert } from './backend';
import { latestLoginEmail } from './mailpit';

/**
 * Slice 1/1.1 journeys against the real API, PostgreSQL and S3-compatible storage. Photos
 * and voice notes go from the browser straight to storage with presigned URLs
 * (cross-origin, CORS) and are then verified by the API. Camera capture and the real iPhone
 * microphone need a device (manual check); here files go to the same inputs the camera and
 * library buttons open, and recordings come from the browsers' fake microphones.
 */

const fixture = (name: string) => fileURLToPath(new URL(`./fixtures/${name}`, import.meta.url));

async function signIn(page: Page, request: APIRequestContext, email: string) {
  await page.goto('/login');
  await page.getByLabel('Електронна адреса').fill(email);
  await page.getByRole('button', { name: 'Отримати посилання' }).click();
  const { code } = await latestLoginEmail(request, email);
  await page.getByLabel('Код із листа').fill(code);
  await page.getByRole('button', { name: 'Увійти' }).click();
  await expect(page.getByRole('heading', { name: 'Мої проєкти' })).toBeVisible();
}

async function newProject(page: Page) {
  await page.getByRole('button', { name: 'Новий проєкт' }).click();
  await expect(page.getByRole('heading', { name: 'Проєкт без назви' })).toBeVisible();
}

const gallery = (page: Page) => page.getByRole('region', { name: /^Фото/ });
const voiceSection = (page: Page) => page.getByRole('region', { name: 'Нотатки', exact: true });
/** Recording controls, docked at the bottom while recording or reviewing. */
const recorder = (page: Page) => page.getByRole('region', { name: 'Запис голосу' });
const categoryChips = (page: Page) => page.getByRole('group', { name: 'Категорія наступних фото' });

/** The library input behind "Choose photos" (what iOS fills after the photo picker). */
const libraryInput = (page: Page) => page.locator('input[type="file"][multiple]');

async function expectImageLoaded(image: Locator) {
  await expect(image).toBeVisible();
  await expect
    .poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0))
    .toBe(true);
}

/** Loads the audio element's source and returns its duration in seconds. */
async function playableDuration(audio: Locator): Promise<number> {
  return audio.evaluate(
    (element: HTMLAudioElement) =>
      new Promise<number>((resolve, reject) => {
        element.preload = 'auto';
        element.onloadedmetadata = () => resolve(element.duration);
        element.onerror = () => reject(new Error(`audio error ${element.error?.code}`));
        element.load();
      }),
  );
}

const NO_RECORDER =
  'This browser build cannot record audio (Playwright WebKit on Linux CI); voice is covered by ' +
  'Chromium in CI, WebKit on macOS and the recorder unit tests';

/** Whether this browser build can actually record from a (fake) microphone. */
async function canRecord(page: Page): Promise<boolean> {
  return page.evaluate(async () => {
    if (typeof MediaRecorder === 'undefined' || !('getUserMedia' in (navigator.mediaDevices ?? {})))
      return false;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      return true;
    } catch {
      return false;
    }
  });
}

async function recordVoiceNote(page: Page, ms = 1500) {
  await page.getByRole('button', { name: 'Записати голос' }).click();
  await expect(recorder(page).getByRole('status')).toContainText('Запис');
  await expect(recorder(page).getByRole('button', { name: 'Зупинити' })).toBeVisible();
  await page.waitForTimeout(ms);
  await recorder(page).getByRole('button', { name: 'Зупинити' }).click();
  await expect(recorder(page).getByText(/Новий запис ·/)).toBeVisible();
}

test('capture per category into one gallery, recategorize, rename, reopen, delete', async ({
  page,
  request,
}, info) => {
  await signIn(page, request, createExpert(`garment-${info.project.name}`));
  await newProject(page);
  const garmentUrl = page.url();

  // Select category → take photo → change category → take photo.
  await expect(categoryChips(page).getByRole('radio', { name: 'Перед' })).toBeChecked();
  await libraryInput(page).setInputFiles(fixture('front.jpg'));
  const front = gallery(page).getByRole('link', { name: 'Відкрити фото 1: Перед' });
  await expectImageLoaded(front.locator('img'));
  await categoryChips(page).getByRole('radio', { name: 'Етикетка' }).check();
  await libraryInput(page).setInputFiles(fixture('label.heic'));
  const label = gallery(page).getByRole('link', { name: 'Відкрити фото 2: Етикетка' });
  await expectImageLoaded(label.locator('img')); // HEIC shown via server-rendered JPEG

  // Rename in the header; text note in the Notes section.
  await page.getByRole('button', { name: 'Перейменувати' }).click();
  await page.getByLabel('Назва').fill('Джинсова куртка');
  await page.getByLabel('Назва').press('Enter');
  await expect(page.getByRole('heading', { name: 'Джинсова куртка' })).toBeVisible();
  await page.locator('summary', { hasText: 'Текстова нотатка' }).click();
  await page.getByRole('textbox', { name: 'Текстова нотатка' }).fill('Потертості на манжетах');
  await page.getByRole('button', { name: 'Зберегти', exact: true }).click();
  await expect(page.getByRole('status')).toHaveText('Збережено');

  // Reopen from the list after a full reload: everything comes back from the server.
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Джинсова куртка' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: 'Текстова нотатка' })).toHaveValue(
    'Потертості на манжетах',
  );
  await page.getByRole('link', { name: 'Усі проєкти' }).click();
  const card = page.getByRole('link', { name: /Джинсова куртка/ });
  await expect(card).toContainText('2 фото');
  await expectImageLoaded(card.locator('img'));
  await card.click();
  await expect(page).toHaveURL(garmentUrl);

  // Photo screen: details, change and remove the category, original download.
  await label.click();
  await expectImageLoaded(page.getByRole('img', { name: 'Фото: Етикетка' }));
  await expect(page.getByText('HEIC', { exact: true })).toBeVisible();
  await expect(page.getByText('96 × 64 пікс.')).toBeVisible();
  const original = await page.request.get(
    (await page.getByRole('link', { name: 'Завантажити оригінал' }).getAttribute('href')) ?? '',
  );
  expect(original.status()).toBe(200);
  expect(original.headers()['content-disposition']).toContain('attachment');
  const chips = page.getByRole('group', { name: 'Категорія' });
  await chips.getByRole('radio', { name: 'Дефекти' }).check();
  await expect(page.getByRole('heading', { name: 'Дефекти' })).toBeVisible();
  await page.getByRole('link', { name: 'Назад до проєкту' }).click();
  const defect = gallery(page).getByRole('link', { name: 'Відкрити фото 2: Дефекти' });
  await expect(defect).toBeVisible();

  await defect.click();
  await chips.getByRole('radio', { name: 'Без категорії' }).check();
  await expect(page.getByRole('heading', { name: 'Фото', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Видалити фото' }).click();
  await page.getByRole('button', { name: 'Видалити остаточно' }).click();
  await expect(page).toHaveURL(garmentUrl);
  await expect(gallery(page).getByRole('link')).toHaveCount(1);

  // Deleting the project is a secondary action, still confirmed.
  await expect(page.getByRole('button', { name: 'Видалити проєкт' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Інші дії' }).click();
  await page.getByRole('button', { name: 'Видалити проєкт' }).click();
  await page.getByRole('button', { name: 'Видалити остаточно' }).click();
  await expect(page.getByRole('heading', { name: 'Мої проєкти' })).toBeVisible();
  await expect(page.getByText(/Ще немає проєктів/)).toBeVisible();
  await page.goto(garmentUrl);
  await expect(page.getByRole('alert')).toContainText('Не знайдено');
});

test('an interrupted upload fails visibly and succeeds on retry', async ({
  page,
  request,
}, info) => {
  test.setTimeout(90_000); // automatic retries back off for ~13 s before asking the expert
  await signIn(page, request, createExpert(`retry-${info.project.name}`));
  await newProject(page);

  let storageDown = true;
  await page.route('**/uploads/**', async (route) => {
    if (storageDown && route.request().method() === 'PUT')
      await route.abort('internetdisconnected');
    else await route.fallback();
  });

  await libraryInput(page).setInputFiles(fixture('front.jpg'));
  await expect(gallery(page).getByText('Не завантажено')).toBeVisible({ timeout: 30_000 });
  await expect(
    gallery(page).getByText('Немає з’єднання з сервером', { exact: false }),
  ).toBeVisible();

  storageDown = false;
  await gallery(page).getByRole('button', { name: 'Повторити' }).click();
  await expectImageLoaded(
    gallery(page).getByRole('link', { name: 'Відкрити фото 1: Перед' }).locator('img'),
  );
  await expect(gallery(page).getByText('Не завантажено')).toHaveCount(0);
});

test('a file that is not an image is rejected with a reason', async ({ page, request }, info) => {
  await signIn(page, request, createExpert(`reject-${info.project.name}`));
  await newProject(page);
  await libraryInput(page).setInputFiles(fixture('not-a-photo.jpg'));
  await expect(gallery(page).getByText('Відхилено')).toBeVisible();
  await expect(
    gallery(page).getByText('Цей тип файлу не підтримується', { exact: false }),
  ).toBeVisible();
  await gallery(page).getByRole('button', { name: 'Прибрати' }).click();
  await expect(gallery(page).getByText('Відхилено')).toHaveCount(0);
});

test('voice notes: record, review, save, play after reload, record another, delete', async ({
  page,
  request,
}, info) => {
  await signIn(page, request, createExpert(`voice-${info.project.name}`));
  await newProject(page);
  test.skip(!(await canRecord(page)), NO_RECORDER);

  await recordVoiceNote(page);
  const review = recorder(page).getByLabel('Прослухати новий запис');
  expect(await playableDuration(review)).toBeGreaterThan(0.5);
  await recorder(page).getByRole('button', { name: 'Зберегти запис' }).click();
  const firstNote = voiceSection(page).getByRole('article', { name: 'Нотатка 1' });
  await expect(firstNote).toBeVisible();

  // Survives closing and reopening: comes back from the server and plays from the API.
  await page.reload();
  await expect(firstNote).toBeVisible();
  const audio = firstNote.getByLabel('Відтворити: Нотатка 1');
  const src = (await audio.getAttribute('src')) ?? '';
  expect(src).toMatch(/^\/api\/v1\/voice-notes\/.+\/audio$/);
  expect(await playableDuration(audio)).toBeGreaterThan(0.5);
  const range = await page.request.get(src, { headers: { Range: 'bytes=0-1' } });
  expect(range.status()).toBe(206);

  await recordVoiceNote(page, 1000);
  await recorder(page).getByRole('button', { name: 'Зберегти запис' }).click();
  await expect(voiceSection(page).getByRole('article', { name: 'Нотатка 2' })).toBeVisible();

  await firstNote.getByRole('button', { name: 'Видалити нотатку' }).click();
  await firstNote.getByRole('button', { name: 'Видалити остаточно' }).click();
  await expect(voiceSection(page).getByRole('article')).toHaveCount(1);
  expect((await page.request.get(src)).status()).toBe(404);
});

test('a recording that was not saved comes back after a reload', async ({
  page,
  request,
}, info) => {
  await signIn(page, request, createExpert(`draft-${info.project.name}`));
  await newProject(page);
  test.skip(!(await canRecord(page)), NO_RECORDER);
  await recordVoiceNote(page);
  await page.waitForTimeout(300); // the local copy is written right after recording stops

  await page.reload();
  const draft = voiceSection(page).getByText(/Новий запис .* Не збережено/);
  await expect(draft).toBeVisible();
  await voiceSection(page).getByRole('button', { name: 'Зберегти запис' }).click();
  await expect(voiceSection(page).getByRole('article', { name: 'Нотатка 1' })).toBeVisible();

  await page.reload(); // the local copy is gone once the server has it
  await expect(voiceSection(page).getByRole('article')).toHaveCount(1);
  await expect(voiceSection(page).getByText(/Не збережено/)).toHaveCount(0);
});

test('an interrupted voice upload can be retried', async ({ page, request }, info) => {
  test.setTimeout(90_000);
  await signIn(page, request, createExpert(`voice-retry-${info.project.name}`));
  await newProject(page);
  test.skip(!(await canRecord(page)), NO_RECORDER);
  let storageDown = true;
  await page.route('**/uploads/**', async (route) => {
    if (storageDown && route.request().method() === 'PUT')
      await route.abort('internetdisconnected');
    else await route.fallback();
  });

  await recordVoiceNote(page);
  await recorder(page).getByRole('button', { name: 'Зберегти запис' }).click();
  await expect(voiceSection(page).getByText(/Не збережено на сервері/)).toBeVisible({
    timeout: 30_000,
  });
  storageDown = false;
  await voiceSection(page).getByRole('button', { name: 'Повторити' }).click();
  await expect(voiceSection(page).getByRole('article', { name: 'Нотатка 1' })).toBeVisible();
});

test.describe('without microphone permission', () => {
  test.use({ permissions: [] }); // WebKit then rejects getUserMedia with NotAllowedError

  test('a denied microphone is explained', async ({ page, request }, info) => {
    // Chromium's fake UI grants everything, so deny explicitly there.
    await page.addInitScript(() => {
      Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
        configurable: true,
        value: () => Promise.reject(new DOMException('denied', 'NotAllowedError')),
      });
    });
    await signIn(page, request, createExpert(`mic-${info.project.name}`));
    await newProject(page);
    const hasRecorder = await page.evaluate(
      () =>
        typeof MediaRecorder !== 'undefined' && 'getUserMedia' in (navigator.mediaDevices ?? {}),
    );
    test.skip(!hasRecorder, NO_RECORDER);
    await page.getByRole('button', { name: 'Записати голос' }).click();
    await expect(recorder(page).getByRole('alert')).toContainText('Немає доступу до мікрофона');
  });
});

test("another expert cannot open someone else's project, photos or voice notes", async ({
  page,
  browser,
  request,
}, info) => {
  await signIn(page, request, createExpert(`owner-${info.project.name}`));
  await newProject(page);
  await libraryInput(page).setInputFiles(fixture('front.jpg'));
  const photoLink = gallery(page).getByRole('link', { name: 'Відкрити фото 1: Перед' });
  await expectImageLoaded(photoLink.locator('img'));
  let audio: string | null = null; // voice part only where the browser can record
  if (await canRecord(page)) {
    await recordVoiceNote(page, 800);
    await recorder(page).getByRole('button', { name: 'Зберегти запис' }).click();
    const note = voiceSection(page).getByRole('article', { name: 'Нотатка 1' });
    await expect(note).toBeVisible();
    audio = await note.getByLabel('Відтворити: Нотатка 1').getAttribute('src');
  }
  const garmentUrl = page.url();
  const thumbnail = (await photoLink.locator('img').getAttribute('src')) ?? '';

  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await signIn(otherPage, other.request, createExpert(`intruder-${info.project.name}`));
  await otherPage.goto(garmentUrl);
  await expect(otherPage.getByRole('alert')).toContainText('Не знайдено');
  expect((await otherPage.request.get(thumbnail)).status()).toBe(404);
  if (audio) expect((await otherPage.request.get(audio)).status()).toBe(404);
  await other.close();

  // Signed-out requests are refused too.
  expect((await request.get(thumbnail)).status()).toBe(401);
  if (audio) expect((await request.get(audio)).status()).toBe(401);
});

import { fileURLToPath } from 'node:url';

import { expect, test, type APIRequestContext, type Locator, type Page } from '@playwright/test';

import { createExpert } from './backend';
import { latestLoginEmail } from './mailpit';

/**
 * Slice 1 journey against the real API, PostgreSQL and S3-compatible storage. Photos go
 * from the browser straight to storage with presigned URLs (cross-origin, CORS) and are
 * then verified by the API. Camera capture itself needs a real iPhone (manual check);
 * here files are supplied to the same inputs the camera and library buttons open.
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

const category = (page: Page, name: string) => page.getByRole('region', { name, exact: true });

/** The library input behind "Choose photos" (what iOS fills after the photo picker). */
const libraryInput = (region: Locator) => region.locator('input[type="file"][multiple]');

async function expectImageLoaded(image: Locator) {
  await expect(image).toBeVisible();
  await expect
    .poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0))
    .toBe(true);
}

test('create a project, add JPEG and HEIC photos, reopen, edit and delete', async ({
  page,
  request,
}, info) => {
  await signIn(page, request, createExpert(`garment-${info.project.name}`));
  await newProject(page);
  const garmentUrl = page.url();

  await libraryInput(category(page, 'Перед')).setInputFiles(fixture('front.jpg'));
  await libraryInput(category(page, 'Етикетка')).setInputFiles(fixture('label.heic'));

  const frontPhoto = category(page, 'Перед').getByRole('link', { name: 'Відкрити фото: Перед' });
  const labelPhoto = category(page, 'Етикетка').getByRole('link', {
    name: 'Відкрити фото: Етикетка',
  });
  await expectImageLoaded(frontPhoto.locator('img'));
  await expectImageLoaded(labelPhoto.locator('img')); // HEIC shown via server-rendered JPEG

  await page.getByLabel('Назва').fill('Джинсова куртка');
  await page.getByLabel('Нотатки').fill('Потертості на манжетах');
  await page.getByRole('button', { name: 'Зберегти' }).click();
  await expect(page.getByRole('status')).toHaveText('Збережено');

  // Reopen from the list after a full reload: everything comes back from the server.
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Джинсова куртка' })).toBeVisible();
  await expect(page.getByLabel('Нотатки')).toHaveValue('Потертості на манжетах');
  await page.getByRole('link', { name: 'Усі проєкти' }).click();
  const card = page.getByRole('link', { name: /Джинсова куртка/ });
  await expect(card).toContainText('2 фото');
  await expectImageLoaded(card.locator('img'));
  await card.click();
  await expect(page).toHaveURL(garmentUrl);

  // Photo viewer: details, recategorize, original download link.
  await category(page, 'Етикетка').getByRole('link', { name: 'Відкрити фото: Етикетка' }).click();
  await expectImageLoaded(page.getByRole('img', { name: 'Фото: Етикетка' }));
  await expect(page.getByText('HEIC', { exact: true })).toBeVisible();
  await expect(page.getByText('96 × 64 пікс.')).toBeVisible();
  const original = await page.request.get(
    (await page.getByRole('link', { name: 'Завантажити оригінал' }).getAttribute('href')) ?? '',
  );
  expect(original.status()).toBe(200);
  expect(original.headers()['content-disposition']).toContain('attachment');
  await page.getByLabel('Категорія').selectOption('defect');
  await expect(page.getByRole('heading', { name: 'Дефекти' })).toBeVisible();

  await page.getByRole('button', { name: 'Видалити фото' }).click();
  await page.getByRole('button', { name: 'Видалити остаточно' }).click();
  await expect(page).toHaveURL(garmentUrl);
  await expect(category(page, 'Дефекти').getByRole('link')).toHaveCount(0);
  await expect(category(page, 'Етикетка').getByRole('link')).toHaveCount(0);
  await expect(frontPhoto).toBeVisible();

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

  const front = category(page, 'Перед');
  await libraryInput(front).setInputFiles(fixture('front.jpg'));
  await expect(front.getByText('Не завантажено')).toBeVisible({ timeout: 30_000 });
  await expect(front.getByText('Немає з’єднання з сервером', { exact: false })).toBeVisible();

  storageDown = false;
  await front.getByRole('button', { name: 'Повторити' }).click();
  await expectImageLoaded(front.getByRole('link', { name: 'Відкрити фото: Перед' }).locator('img'));
  await expect(front.getByText('Не завантажено')).toHaveCount(0);
});

test('a file that is not an image is rejected with a reason', async ({ page, request }, info) => {
  await signIn(page, request, createExpert(`reject-${info.project.name}`));
  await newProject(page);
  const fabric = category(page, 'Тканина');
  await libraryInput(fabric).setInputFiles(fixture('not-a-photo.jpg'));
  await expect(fabric.getByText('Відхилено')).toBeVisible();
  await expect(fabric.getByText('Цей тип файлу не підтримується', { exact: false })).toBeVisible();
  await fabric.getByRole('button', { name: 'Прибрати' }).click();
  await expect(fabric.getByText('Відхилено')).toHaveCount(0);
});

test("another expert cannot open someone else's project or photos", async ({
  page,
  browser,
  request,
}, info) => {
  await signIn(page, request, createExpert(`owner-${info.project.name}`));
  await newProject(page);
  await libraryInput(category(page, 'Перед')).setInputFiles(fixture('front.jpg'));
  const photoLink = category(page, 'Перед').getByRole('link', { name: 'Відкрити фото: Перед' });
  await expectImageLoaded(photoLink.locator('img'));
  const garmentUrl = page.url();
  const thumbnail = (await photoLink.locator('img').getAttribute('src')) ?? '';

  const other = await browser.newContext();
  const otherPage = await other.newPage();
  await signIn(otherPage, other.request, createExpert(`intruder-${info.project.name}`));
  await otherPage.goto(garmentUrl);
  await expect(otherPage.getByRole('alert')).toContainText('Не знайдено');
  expect((await otherPage.request.get(thumbnail)).status()).toBe(404);
  await other.close();

  // Signed-out requests are refused too.
  expect((await request.get(thumbnail)).status()).toBe(401);
});

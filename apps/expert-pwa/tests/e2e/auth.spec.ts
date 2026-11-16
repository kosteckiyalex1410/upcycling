import { expect, test, type Page } from '@playwright/test';

import { createExpert } from './backend';
import { latestLoginEmail } from './mailpit';

async function requestLoginEmail(page: Page, email: string) {
  await page.goto('/');
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole('heading', { name: 'Вхід' })).toBeVisible();
  await page.getByLabel('Електронна адреса').fill(email);
  await page.getByRole('button', { name: 'Отримати посилання' }).click();
  await expect(page.getByRole('heading', { name: 'Перевірте пошту' })).toBeVisible();
}

test('magic link sign-in, language preference and sign-out', async ({ page, request }, info) => {
  const email = createExpert(info.project.name);
  await requestLoginEmail(page, email);
  const { link } = await latestLoginEmail(request, email);

  await page.goto(link);
  await expect(page.getByRole('heading', { name: 'Мої проєкти' })).toBeVisible();
  await expect(page).toHaveURL(/\/$/); // token removed from the address bar
  await expect(page.locator('html')).toHaveAttribute('lang', 'uk');

  await page.getByRole('link', { name: 'Налаштування' }).click();
  await page.getByRole('radio', { name: 'English' }).check();
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();

  // The preference is stored server-side: it survives clearing local storage.
  await page.evaluate(() => window.localStorage.clear());
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');

  await page.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto('/settings');
  await expect(page).toHaveURL(/\/login$/);
});

test('one-time code sign-in for the installed PWA', async ({ page, request }, info) => {
  const email = createExpert(info.project.name);
  await requestLoginEmail(page, email);
  const { code } = await latestLoginEmail(request, email);

  await page.getByLabel('Код із листа').fill(code);
  await page.getByRole('button', { name: 'Увійти' }).click();
  await expect(page.getByRole('heading', { name: 'Мої проєкти' })).toBeVisible();
});

test('a magic link cannot be reused', async ({ page, browser, request }, info) => {
  const email = createExpert(info.project.name);
  await requestLoginEmail(page, email);
  const { link } = await latestLoginEmail(request, email);
  await page.goto(link);
  await expect(page.getByRole('heading', { name: 'Мої проєкти' })).toBeVisible();

  const otherContext = await browser.newContext();
  const otherPage = await otherContext.newPage();
  await otherPage.goto(link);
  await expect(otherPage.getByRole('alert')).toContainText('Посилання недійсне');
  await otherContext.close();
});

test('the web app manifest is served', async ({ request }) => {
  const response = await request.get('/manifest.webmanifest');
  expect(response.ok()).toBe(true);
  const manifest = (await response.json()) as { display: string; icons: unknown[] };
  expect(manifest.display).toBe('standalone');
  expect(manifest.icons.length).toBeGreaterThanOrEqual(2);
});

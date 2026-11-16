import { expect, type APIRequestContext } from '@playwright/test';

import { MAILPIT_URL } from './env';

type SearchResult = { messages: { ID: string }[] };
type Message = { Text: string };

/** Waits for the newest email to `to` in Mailpit and returns its link and code. */
export async function latestLoginEmail(request: APIRequestContext, to: string) {
  let messageId = '';
  await expect
    .poll(async () => {
      const response = await request.get(`${MAILPIT_URL}/api/v1/search`, {
        params: { query: `to:"${to}"` },
      });
      const result = (await response.json()) as SearchResult;
      messageId = result.messages[0]?.ID ?? '';
      return messageId;
    })
    .not.toBe('');
  const message = (await (
    await request.get(`${MAILPIT_URL}/api/v1/message/${messageId}`)
  ).json()) as Message;
  const link = /https?:\/\/\S+\/auth\/verify#token=[\w-]+/.exec(message.Text)?.[0];
  const code = /^(\d{6})$/m.exec(message.Text)?.[1];
  if (!link || !code) throw new Error('Login email did not contain a link and a code');
  return { link, code };
}

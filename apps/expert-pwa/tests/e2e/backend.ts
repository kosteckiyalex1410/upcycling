import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { BACKEND_ENV } from './env';

const BACKEND_DIR = fileURLToPath(new URL('../../../../backend', import.meta.url));

/** Runs a backend command (`uv run ...`) against the e2e database. */
export function backend(...args: string[]): string {
  return execFileSync('uv', ['run', ...args], {
    cwd: BACKEND_DIR,
    env: { ...process.env, ...BACKEND_ENV },
    encoding: 'utf8',
  });
}

/** Creates a fresh expert account so each test starts from a known state (locale `uk`). */
export function createExpert(label: string): string {
  const email = `expert-${label}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  backend('python', '-m', 'app.cli', 'create-user', '--email', email, '--locale', 'uk');
  return email;
}

export const PWA_ORIGIN = 'http://localhost:4173';
export const MAILPIT_URL = process.env.MAILPIT_URL ?? 'http://localhost:8025';

/** Backend configuration for e2e runs; isolated database, Mailpit SMTP, relaxed rate limits. */
export const BACKEND_ENV: Record<string, string> = {
  UPCYCLING_ENVIRONMENT: 'development',
  UPCYCLING_DATABASE_URL:
    process.env.UPCYCLING_E2E_DATABASE_URL ??
    'postgresql+psycopg://upcycling:upcycling@localhost:55432/upcycling_e2e',
  UPCYCLING_PUBLIC_ORIGIN: PWA_ORIGIN,
  UPCYCLING_SESSION_COOKIE_SECURE: 'false',
  UPCYCLING_SMTP_HOST: 'localhost',
  UPCYCLING_SMTP_PORT: '1025',
  UPCYCLING_LOGIN_RATE_LIMIT_PER_EMAIL: '1000',
  UPCYCLING_LOGIN_RATE_LIMIT_PER_IP: '1000',
};

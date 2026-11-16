/**
 * Platform port for small per-device preferences (ARCHITECTURE.md §9).
 * The browser implementation uses localStorage; a native shell can provide its own.
 * Best effort: storage can be unavailable (private mode, eviction) and must never throw.
 */
export interface PreferenceStore {
  get(key: string): string | null;
  set(key: string, value: string): void;
}

export function createBrowserPreferenceStore(prefix = 'upcycling.'): PreferenceStore {
  return {
    get(key) {
      try {
        return window.localStorage.getItem(prefix + key);
      } catch {
        return null;
      }
    },
    set(key, value) {
      try {
        window.localStorage.setItem(prefix + key, value);
      } catch {
        // Ignore: the server-side preference remains the source of truth once signed in.
      }
    },
  };
}

export function createMemoryPreferenceStore(initial: Record<string, string> = {}): PreferenceStore {
  const values = new Map(Object.entries(initial));
  return {
    get: (key) => values.get(key) ?? null,
    set: (key, value) => void values.set(key, value),
  };
}

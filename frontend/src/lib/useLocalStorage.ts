import { useCallback, useEffect, useState } from "react";

/**
 * One typed, private-mode-safe localStorage hook (M4 / foundation F0.2).
 *
 * Previously every panel hand-rolled its own read/try-catch/key constant
 * (Face messages, MetricsStrip selected/showValues, CognitiveSphere settings).
 * Route them all through this instead.
 *
 * - JSON-serialized by default.
 * - `sanitize` lets callers validate/migrate the parsed value (e.g. drop unknown
 *   metric keys, coerce legacy "1"/"0" booleans); on any failure it falls back to
 *   `initial`, so a corrupt or incompatible value can never crash the UI.
 * - Reads lazily once in the state initializer; writes on change.
 */
export interface LocalStorageOptions<T> {
  sanitize?: (raw: unknown) => T;
}

export function readLocalStorage<T>(key: string, initial: T, opts?: LocalStorageOptions<T>): T {
  try {
    const raw = localStorage.getItem(key);
    if (raw == null) return initial;
    const parsed = JSON.parse(raw) as unknown;
    return opts?.sanitize ? opts.sanitize(parsed) : (parsed as T);
  } catch {
    return initial;
  }
}

export function useLocalStorage<T>(
  key: string,
  initial: T,
  opts?: LocalStorageOptions<T>,
): [T, (value: T | ((prev: T) => T)) => void] {
  const [value, setValue] = useState<T>(() => readLocalStorage(key, initial, opts));

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* private mode / quota — preferences just won't persist this session */
    }
  }, [key, value]);

  const set = useCallback((v: T | ((prev: T) => T)) => setValue(v), []);
  return [value, set];
}

import { useEffect, useState } from "react";

/**
 * The companion/workshop mode flag (Companion & Presence plan §2 C0).
 *
 * One codebase, one runtime, one telemetry stream — the mode is a *lens*, never
 * a branch. It only changes which chrome (nav, labels, home) wraps the same
 * rooms.
 *
 * Semantics that must not drift:
 * - UNSET → workshop. Every existing user predates the flag; they must get
 *   today's behavior exactly. Companion becomes default only via the FirstWake
 *   answer on a genuinely fresh runtime.
 * - COMPANION_ROOMS is the nav-depth rule: standing in one of these with
 *   mode=companion shows the 3-item companion nav; standing anywhere else shows
 *   the full workshop nav regardless of mode.
 */

export type OrrinMode = "companion" | "workshop";

export const MODE_KEY = "orrin.mode.v1";

export const COMPANION_ROOMS = ["/orrin", "/timeline", "/settings"] as const;

const MODE_EVENT = "orrin:mode";

export function readMode(): OrrinMode {
  try {
    return localStorage.getItem(MODE_KEY) === "companion" ? "companion" : "workshop";
  } catch {
    return "workshop";
  }
}

export function writeMode(mode: OrrinMode): void {
  try {
    localStorage.setItem(MODE_KEY, mode);
  } catch {
    /* private mode — the choice just won't persist */
  }
  window.dispatchEvent(new Event(MODE_EVENT));
}

export function isCompanionRoom(pathname: string): boolean {
  return COMPANION_ROOMS.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

/** Hook form: live mode, updating across same-tab writes and other tabs. */
export function useMode(): OrrinMode {
  const [mode, setMode] = useState<OrrinMode>(readMode);
  useEffect(() => {
    const sync = () => setMode(readMode());
    window.addEventListener(MODE_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(MODE_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  return mode;
}

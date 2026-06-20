import { useEffect, useRef } from "react";

/**
 * Cross-box provenance navigation (UI_FIXES Fix 4 step 4 / Fix 10.3): a tiny
 * window-event bus so one panel can send the viewer to the owning panel —
 * a goal in GoalsPanel, a function node on the CognitiveSphere, the affect
 * rings, a memory store. This is what turns separate panels into one
 * navigable system.
 *
 * Boxes register a `box-<name>` element id (the same convention the L0
 * vital-signs chips already jump by) and, when they can open a specific item,
 * subscribe with useNavTarget.
 */

const EVENT = "orrin:navigate";

export function navigateTo(box: string, id?: string): void {
  document.getElementById(`box-${box}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  if (id != null) {
    window.dispatchEvent(new CustomEvent(EVENT, { detail: { box, id } }));
  }
}

/** Subscribe a panel to navigation targets aimed at it. Handler identity is
 *  kept in a ref, so callers can pass inline closures safely. */
export function useNavTarget(box: string, handler: (id: string) => void): void {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    const on = (e: Event) => {
      const d = (e as CustomEvent).detail as { box?: string; id?: string } | undefined;
      if (d?.box === box && d.id != null) ref.current(String(d.id));
    };
    window.addEventListener(EVENT, on);
    return () => window.removeEventListener(EVENT, on);
  }, [box]);
}

/** Where a conscious moment's `source` should navigate (Fix 4 step 4).
 *  Returns null for sources with no owning box. */
export function boxForSource(source?: string): string | null {
  switch ((source || "").toLowerCase()) {
    case "goal":
      return "goals-panel";
    case "affect":
    case "signal":
      return "affect";
    case "memory":
      return "memory";
    case "monitor":
    case "breakthrough":
    case "binding":
      return "consciousness";
    default:
      return null;
  }
}

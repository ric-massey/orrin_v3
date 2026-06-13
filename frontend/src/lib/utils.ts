import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn class-name combiner: conditional classes + Tailwind conflict resolution. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Clamp a number to [lo, hi]. */
export function clamp(n: number, lo = 0, hi = 1) {
  return Math.max(lo, Math.min(hi, n));
}

/** Format an epoch-seconds timestamp as HH:MM:SS. */
export function fmtTime(ts?: number) {
  const d = ts ? new Date(ts * 1000) : new Date();
  return d.toLocaleTimeString([], { hour12: false });
}

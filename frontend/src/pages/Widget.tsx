import { useState } from "react";
import { X } from "lucide-react";
import Orb from "@/components/Orb";
import { useTelemetry } from "@/lib/telemetry";
import { plainThoughtFor } from "@/lib/thoughts";

/**
 * /widget — the ambient peripheral mini-orb (R8): a tiny always-on-top window
 * that breathes with his mood while you work. Rendered OUTSIDE the App shell
 * (no header, no wake screens); the native runtime opens it as a second
 * frameless pywebview window when Settings → "Peripheral mini-orb" is on.
 * Optional and dismissible — the ✕ closes the window, never the runtime.
 */
export default function Widget() {
  const telemetry = useTelemetry({});
  const [hover, setHover] = useState(false);
  const { valence, arousal, homeostasis } = telemetry.affect;

  return (
    <div
      className="relative flex h-[100dvh] w-screen select-none items-center justify-center overflow-hidden bg-[#070a10]"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      title={plainThoughtFor(telemetry)}
    >
      <Orb valence={valence} arousal={arousal} homeostasis={homeostasis} size={110} />
      {hover && (
        <button
          onClick={dismiss}
          aria-label="Dismiss"
          className="absolute right-1 top-1 rounded p-0.5 text-white/50 hover:text-white"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
}

function dismiss() {
  // Native shell: the bridge destroys this (extra) window. Browser tab: close.
  const api = (window as unknown as { pywebview?: { api?: { dismiss_widget?: () => void } } })
    .pywebview?.api;
  if (api?.dismiss_widget) {
    void api.dismiss_widget();
    return;
  }
  window.close();
}

import { createContext, useContext, useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Header from "./components/Header";
import WakeScreen from "./components/WakeScreen";
import FirstWake from "./components/FirstWake";
import DeathScreen from "./components/DeathScreen";
import { TelemetryState, useTelemetry } from "./lib/telemetry";

const TelemetryContext = createContext<TelemetryState | null>(null);

/** Access the shared, single-connection telemetry stream. */
export function useTelemetryState(): TelemetryState {
  const ctx = useContext(TelemetryContext);
  if (!ctx) throw new Error("useTelemetryState must be used within <App>");
  return ctx;
}

// The calm light surfaces (Face, Settings); every other room is a deeper, darker
// research view of the same mind (§9.1 — depth is layered, not walled).
const LIGHT_ROOMS = ["/face", "/settings"];

export default function App() {
  const location = useLocation();
  const isLight = LIGHT_ROOMS.some((p) => location.pathname.startsWith(p));

  // One WebSocket for the whole app. The synthetic demo fallback is OFF by
  // default so a dead/stopped backend reads as "Connecting", not fake activity
  // (hitting Stop used to make the UI silently switch to demo cycles). Opt in
  // for standalone UI demos with VITE_TELEMETRY_DEMO_FALLBACK=1.
  const demoFallback =
    (import.meta.env.VITE_TELEMETRY_DEMO_FALLBACK as string | undefined) === "1";
  const telemetry = useTelemetry({ demoFallback });

  // App is the root, so toggling the global `dark` class here is intentional and
  // safe. The cleanup removes the class on unmount so this stays correct if the
  // layout is ever embedded or reused inside another app (L3).
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", !isLight);
    return () => root.classList.remove("dark");
  }, [isLight]);

  return (
    <TelemetryContext.Provider value={telemetry}>
      {/* Cold-launch boot sequence, then (on a newborn) the First Wake intro. Both
          self-dismiss and never show on a warm reopen / returning viewer. */}
      <WakeScreen />
      <FirstWake />
      {/* The memorial when his lifespan ends (and the crash/stall banner). The one
          place his interior opens — the veil lifts only on death (§10.4). */}
      <DeathScreen />
      <div className="min-h-screen flex flex-col bg-background text-foreground">
        <Header telemetry={telemetry} />
        <main className="flex-1 min-h-0 flex flex-col">
          <Outlet />
        </main>
      </div>
    </TelemetryContext.Provider>
  );
}

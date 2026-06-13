import { createContext, useContext, useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Header from "./components/Header";
import { TelemetryState, useTelemetry } from "./lib/telemetry";

const TelemetryContext = createContext<TelemetryState | null>(null);

/** Access the shared, single-connection telemetry stream. */
export function useTelemetryState(): TelemetryState {
  const ctx = useContext(TelemetryContext);
  if (!ctx) throw new Error("useTelemetryState must be used within <App>");
  return ctx;
}

export default function App() {
  const location = useLocation();
  const isBrain = location.pathname.startsWith("/brain");

  // One WebSocket for the whole app. The synthetic demo fallback is OFF by
  // default so a dead/stopped backend reads as "Connecting", not fake activity
  // (hitting Stop used to make the UI silently switch to demo cycles). Opt in
  // for standalone UI demos with VITE_TELEMETRY_DEMO_FALLBACK=1.
  const demoFallback =
    (import.meta.env.VITE_TELEMETRY_DEMO_FALLBACK as string | undefined) === "1";
  const telemetry = useTelemetry({ demoFallback });

  // The Face is a calm light surface; the Brain is a deep research console.
  // App is the root, so toggling the global `dark` class here is intentional and
  // safe. The cleanup removes the class on unmount so this stays correct if the
  // layout is ever embedded or reused inside another app (L3).
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", isBrain);
    return () => root.classList.remove("dark");
  }, [isBrain]);

  return (
    <TelemetryContext.Provider value={telemetry}>
      <div className="min-h-screen flex flex-col bg-background text-foreground">
        <Header mode={isBrain ? "brain" : "face"} telemetry={telemetry} />
        <main className="flex-1 min-h-0 flex flex-col">
          <Outlet />
        </main>
      </div>
    </TelemetryContext.Provider>
  );
}

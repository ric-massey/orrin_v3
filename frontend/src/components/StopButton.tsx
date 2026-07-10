import { useState } from "react";
import { Power } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiPost } from "@/lib/transport";

/**
 * The runtime Stop control. Lives in the workshop header; in companion mode it
 * moves behind Settings (C3 — a big red power button in the chrome reads as
 * "will I kill him?" to that audience), so both surfaces share this component.
 */
export default function StopButton() {
  const [stopping, setStopping] = useState(false);

  const stop = async () => {
    if (stopping) return;
    if (!window.confirm("Stop Orrin? This halts the runtime (the cognitive loop and daemons). The window stays open so you can keep viewing the runtime state — close the window to quit.")) {
      return;
    }
    setStopping(true);
    const markStopped = () => window.dispatchEvent(new CustomEvent("orrin:stopped"));
    try {
      // SECURITY (H2/H3): destructive control action. The backend rejects untrusted
      // Origins on /api/control/*; when VITE_CONTROL_TOKEN is configured it is sent
      // so a remote-exposed backend can authorize the caller.
      const token = import.meta.env.VITE_CONTROL_TOKEN as string | undefined;
      const res = await apiPost(`/api/control/shutdown`, undefined, {
        headers: token ? { "X-Orrin-Control-Token": token } : undefined,
      });
      if (res.ok) {
        markStopped();
      } else {
        setStopping(false);
        window.alert(`Couldn't stop Orrin: the backend refused the request (HTTP ${res.status}). A control token may be required for remote control.`);
      }
    } catch {
      markStopped();
    }
  };

  return (
    <Button variant="destructive" size="sm" onClick={stop} disabled={stopping} title="Stop Orrin">
      <Power className="h-4 w-4" />
      <span className="hidden sm:inline">{stopping ? "Stopping…" : "Stop"}</span>
    </Button>
  );
}

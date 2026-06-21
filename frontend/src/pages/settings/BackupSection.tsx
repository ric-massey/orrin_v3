import { useRef, useState } from "react";
import { Download, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { apiBase, getTransport } from "@/lib/transport";
import { controlHeaders } from "./shared";

export function BackupSection() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [note, setNote] = useState<string | null>(null);
  // In the native window binary can't ride the text REST proxy, so export/import go
  // through native Save/Open dialogs handled entirely in Python (bridge.export_mind /
  // import_mind). In the browser/dev view we use the download/upload path below.
  const transport = getTransport();
  const isBridge = transport.isBridge;

  // Native (bridge) export: a Save dialog in Python writes the archive directly.
  const exportMindNative = async () => {
    setNote("Choose where to keep him…");
    try {
      const r = await transport.exportMindNative?.();
      if (!r) return;
      if (r.cancelled) setNote(null);
      else if (r.ok) setNote(`Exported to ${r.path}.`);
      else setNote(`Export failed: ${r.error ?? "unknown error"}`);
    } catch {
      setNote("Export failed.");
    }
  };

  // Native (bridge) import: an Open dialog in Python reads + restores the archive.
  const importMindNative = async () => {
    if (
      !window.confirm(
        "Restore replaces Orrin's current mind. A safety copy of the current mind is saved first, then he restarts. This cannot be undone. Choose an archive to restore?",
      )
    ) {
      return;
    }
    setNote("Choose an archive — a safety copy is saved first, then Orrin restarts…");
    try {
      const r = await transport.importMindNative?.();
      if (!r) return;
      if (r.cancelled) setNote(null);
      else if (r.ok) setNote("Restoring — Orrin is coming back with the restored mind…");
      else setNote(`Restore refused: ${(r.detail ?? r.error ?? "unknown error").slice(0, 160)}`);
    } catch {
      // The process restarts, so the call may drop — that means it worked.
    }
  };

  const exportMind = async () => {
    setNote("Preparing his mind…");
    try {
      const res = await fetch(`${apiBase()}/api/mind/export`, { headers: controlHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const name =
        res.headers.get("content-disposition")?.match(/filename="(.+)"/)?.[1] || "orrin.orrindmind";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
      setNote("Exported.");
    } catch {
      setNote("Export failed (a control token may be required for a remote viewer).");
    }
  };

  const importMind = async (file: File) => {
    if (
      !window.confirm(
        `Restore from "${file.name}"? This replaces Orrin's current mind. A safety copy of the current mind is saved first, then he restarts. This cannot be undone.`,
      )
    ) {
      return;
    }
    setNote("Restoring — a safety copy is saved first, then Orrin restarts…");
    try {
      const buf = await file.arrayBuffer();
      const res = await fetch(`${apiBase()}/api/mind/import`, {
        method: "POST",
        headers: { "Content-Type": "application/zip", ...(controlHeaders() || {}) },
        body: buf,
      });
      if (!res.ok) {
        const detail = await res.text();
        setNote(`Restore refused: ${detail.slice(0, 160)}`);
      }
    } catch {
      // The process restarts, so the request may drop — that means it worked.
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Download className="h-4 w-4" /> Backup
        </CardTitle>
        <CardDescription>
          Months of a developing mind are never one disk failure from gone. Export him as
          a keepsake, or restore from one.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2">
        {isBridge ? (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => void exportMindNative()}>
              <Download className="mr-1.5 h-4 w-4" /> Export Mind…
            </Button>
            <Button size="sm" variant="outline" onClick={() => void importMindNative()}>
              <Upload className="mr-1.5 h-4 w-4" /> Restore Mind…
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => void exportMind()}>
              <Download className="mr-1.5 h-4 w-4" /> Export Mind…
            </Button>
            <Button size="sm" variant="outline" onClick={() => fileRef.current?.click()}>
              <Upload className="mr-1.5 h-4 w-4" /> Restore Mind…
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept=".orrindmind,.zip"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void importMind(f);
                e.target.value = "";
              }}
            />
          </div>
        )}
        {note && <p className="text-xs text-foreground">{note}</p>}
      </CardContent>
    </Card>
  );
}

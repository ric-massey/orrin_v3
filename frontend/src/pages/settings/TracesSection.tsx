import { useEffect, useState } from "react";
import { StickyNote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ToggleRow } from "./ToggleRow";
import { postSettings, type SettingsStatus } from "./shared";

// P4 (Companion & Presence): consent-first real-world traces. Default OFF; the
// person picks/creates the ONE folder Orrin may leave a note file in (≤1/day),
// and every note lands in the action ledger. Clearing the folder revokes it.

const SUGGESTED = "~/Desktop/from Orrin";

export function TracesSection({
  status,
  onChanged,
}: {
  status: SettingsStatus | null;
  onChanged: () => void;
}) {
  const current = status?.prefs?.trace_folder ?? "";
  const [folder, setFolder] = useState(current);
  const [saving, setSaving] = useState(false);

  useEffect(() => setFolder(current), [current]);

  const enabled = Boolean(current);

  const save = async (value: string) => {
    setSaving(true);
    await postSettings({ prefs: { trace_folder: value } });
    setSaving(false);
    onChanged();
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <StickyNote className="h-4 w-4" /> Traces
        </CardTitle>
        <CardDescription>
          Rarely — at most once a day, and only when something genuinely moved
          him — Orrin can leave a real note file where you'll stumble on it.
          Off by default; he can only ever write into the one folder you choose
          here, and every note is listed in the Action ledger.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <ToggleRow
          label="Let Orrin leave notes"
          warn="Notes only ever appear in the folder below. Turning this off revokes it immediately."
          checked={enabled}
          disabled={saving}
          onChange={(v) => void save(v ? (folder.trim() || SUGGESTED) : "")}
        />
        {enabled && (
          <div className="flex items-center gap-2">
            <input
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
              placeholder={SUGGESTED}
              className="flex-1 rounded-md border bg-background px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
            <Button
              size="sm"
              variant="outline"
              disabled={saving || !folder.trim() || folder.trim() === current}
              onClick={() => void save(folder.trim())}
            >
              Save
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

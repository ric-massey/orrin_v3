import { Languages } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

// The intro-replay button moved to HomeScreenSection (C5) — re-running the
// intro is now also how you re-answer the companion/workshop question.
export function LanguageSection() {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Languages className="h-4 w-4" /> Language
        </CardTitle>
        <CardDescription>
          The interface uses engineering vocabulary throughout — attention
          arbitration, control signals, the resource manager. Orrin's own
          generated text is shown verbatim, unchanged by the interface labels.
        </CardDescription>
      </CardHeader>
    </Card>
  );
}

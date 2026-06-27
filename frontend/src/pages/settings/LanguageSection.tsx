import { Languages, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

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
      <CardContent className="space-y-3">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => window.dispatchEvent(new Event("orrin:meet"))}
        >
          <Sparkles className="mr-1.5 h-4 w-4" /> Replay the intro
        </Button>
      </CardContent>
    </Card>
  );
}

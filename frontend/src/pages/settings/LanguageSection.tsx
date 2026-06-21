import { Languages, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { setLexMode, useLexicon } from "@/lib/lexicon";

export function LanguageSection() {
  const { mode } = useLexicon();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Languages className="h-4 w-4" /> Language
        </CardTitle>
        <CardDescription>
          How Orrin describes himself to you. This re-labels the interface only — his
          own words are identical either way.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <DialectButton active={mode === "bio"} onClick={() => setLexMode("bio")} title="As a mind"
            sub="Consciousness, Affect, Life Support" />
          <DialectButton active={mode === "eng"} onClick={() => setLexMode("eng")} title="As a machine"
            sub="Attention arbitration, Resource Manager" />
        </div>
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

function DialectButton({
  active,
  onClick,
  title,
  sub,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  sub: string;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "flex-1 rounded-lg border px-3 py-2 text-left transition-colors",
        active ? "border-primary bg-muted" : "border-border hover:bg-muted",
      )}
    >
      <div className="text-sm font-medium">{title}</div>
      <div className="text-xs text-muted-foreground">{sub}</div>
    </button>
  );
}

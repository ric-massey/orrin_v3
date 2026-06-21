import { cn } from "@/lib/utils";

export function ToggleRow({
  label,
  warn,
  checked,
  disabled,
  disabledNote,
  onChange,
}: {
  label: string;
  warn: string;
  checked: boolean;
  disabled?: boolean;
  disabledNote?: string;
  onChange: (v: boolean) => void | Promise<void>;
}) {
  return (
    <label className={cn("flex items-start gap-3", disabled && "opacity-50")}>
      <input
        type="checkbox"
        className="mt-0.5 h-4 w-4 shrink-0"
        checked={checked}
        disabled={disabled}
        onChange={(e) => void onChange(e.target.checked)}
      />
      <span className="space-y-0.5">
        <span className="block text-sm">{label}</span>
        <span className="block text-xs text-muted-foreground">{disabledNote || warn}</span>
      </span>
    </label>
  );
}

import { ChevronUp } from "lucide-react";
import type { Mode } from "@/api/types";
import { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { PICKABLE, labelOf } from "./modes";

export function ModePicker(props: { mode: Mode | null; onPick: (mode: Mode) => void }) {
  const { mode, onPick } = props;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={`Mode: ${labelOf(mode)}`}
        data-mode={mode ?? "unknown"}
        className={cn(
          "flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-[14px] font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring",
          mode === "auto" ? "border-accent text-accent" : "border-rule text-ink-2",
        )}
      >
        {labelOf(mode)}
        <ChevronUp aria-hidden className="size-3.5" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top">
        <DropdownMenuRadioGroup
          value={mode ?? ""}
          onValueChange={(next) => {
            onPick(next as Mode);
          }}
        >
          {PICKABLE.map((one) => (
            <DropdownMenuRadioItem key={one.mode} value={one.mode}>
              <b className="text-[14px] font-semibold">{one.label}</b>
              <span className="text-[13px] leading-snug text-ink-2">{one.hint}</span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

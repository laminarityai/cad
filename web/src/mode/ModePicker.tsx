import { ChevronUp } from "lucide-react";
import type { Mode } from "@/api/types";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { PICKABLE, labelOf } from "./modes";

export function ModePicker(props: { mode: Mode | null; disabled?: boolean; onPick: (mode: Mode) => void }) {
  const { mode, disabled, onPick } = props;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild disabled={disabled}>
        <Button
          variant="outline"
          size="sm"
          aria-label={`Mode: ${labelOf(mode)}`}
          data-mode={mode ?? "unknown"}
          className={cn(mode === "plan" && "border-res text-res", mode === "auto" && "border-accent text-accent")}
        >
          {labelOf(mode)}
          <ChevronUp aria-hidden />
        </Button>
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
              <b className="font-mono text-xs">{one.label}</b>
              <span className="text-xs text-ink-2">{one.hint}</span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

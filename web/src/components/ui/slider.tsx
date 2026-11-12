import * as React from "react";
import { Slider as Primitive } from "@base-ui/react/slider";
import { cn } from "@/lib/utils";

/** One thumb. `label` names the thumb for a screen reader, which the arrow keys, Home, End and Page Up and Down
 * then move. `valueText` is what it reads out, when the bare number would not say enough. */
function Slider({
  label,
  valueText,
  className,
  ...props
}: Omit<React.ComponentProps<typeof Primitive.Root<number>>, "children"> & { label: string; valueText?: string }) {
  return (
    <Primitive.Root<number> data-slot="slider" className={cn("w-full", className)} {...props}>
      <Primitive.Control className="flex h-6 w-full touch-none select-none items-center">
        <Primitive.Track className="h-1 w-full rounded-full bg-rule">
          <Primitive.Indicator className="rounded-full bg-accent" />
          <Primitive.Thumb
            getAriaLabel={() => label}
            {...(valueText === undefined ? {} : { getAriaValueText: () => valueText })}
            className="size-4 rounded-full border border-rule bg-panel shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </Primitive.Track>
      </Primitive.Control>
    </Primitive.Root>
  );
}

export { Slider };

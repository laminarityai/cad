import * as React from "react";
import { Collapsible as Primitive } from "@base-ui/react/collapsible";
import { cn } from "@/lib/utils";

const Collapsible = Primitive.Root;

/** A trigger is a group, so an icon inside it turns with `group-data-[panel-open]:`. */
function CollapsibleTrigger({ className, ...props }: React.ComponentProps<typeof Primitive.Trigger>) {
  return <Primitive.Trigger data-slot="collapsible-trigger" className={cn("group", className)} {...props} />;
}

function CollapsiblePanel({ className, ...props }: React.ComponentProps<typeof Primitive.Panel>) {
  return (
    <Primitive.Panel
      data-slot="collapsible-panel"
      className={cn(
        "h-(--collapsible-panel-height) overflow-hidden transition-[height] duration-150 data-[ending-style]:h-0 data-[starting-style]:h-0",
        className,
      )}
      {...props}
    />
  );
}

export { Collapsible, CollapsibleTrigger, CollapsiblePanel };

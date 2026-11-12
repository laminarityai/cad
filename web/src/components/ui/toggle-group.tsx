import * as React from "react";
import { Toggle as Item } from "@base-ui/react/toggle";
import { ToggleGroup as Primitive } from "@base-ui/react/toggle-group";
import { cn } from "@/lib/utils";

const ToggleGroup = Primitive;

/** A pressed item carries `data-pressed`, so style it with `data-[pressed]:`. */
function ToggleGroupItem({ className, ...props }: React.ComponentProps<typeof Item>) {
  return <Item data-slot="toggle-group-item" className={cn("outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...props} />;
}

export { ToggleGroup, ToggleGroupItem };

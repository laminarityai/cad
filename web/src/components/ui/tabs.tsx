import * as React from "react";
import { Tabs as Primitive } from "@base-ui/react/tabs";
import { cn } from "@/lib/utils";

const Tabs = Primitive.Root;

function TabsList({ className, ...props }: React.ComponentProps<typeof Primitive.List>) {
  return <Primitive.List data-slot="tabs-list" className={cn("outline-none", className)} {...props} />;
}

/** A selected tab carries `data-active`, so style it with `data-[active]:`. */
function TabsTab({ className, ...props }: React.ComponentProps<typeof Primitive.Tab>) {
  return <Primitive.Tab data-slot="tabs-tab" className={cn("outline-none focus-visible:ring-2 focus-visible:ring-ring", className)} {...props} />;
}

function TabsPanel({ className, ...props }: React.ComponentProps<typeof Primitive.Panel>) {
  return <Primitive.Panel data-slot="tabs-panel" className={cn("outline-none", className)} {...props} />;
}

export { Tabs, TabsList, TabsTab, TabsPanel };

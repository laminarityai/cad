import * as React from "react";
import { Menu } from "@base-ui/react/menu";
import { cn } from "@/lib/utils";

const DropdownMenu = Menu.Root;
const DropdownMenuTrigger = Menu.Trigger;

const ITEM = "flex cursor-default flex-col gap-0.5 border-t border-rule-2 px-3 py-2.5 text-left outline-none first:border-t-0 data-[highlighted]:bg-muted";

function DropdownMenuContent({
  className,
  sideOffset = 6,
  align,
  ...props
}: React.ComponentProps<typeof Menu.Popup> & Pick<React.ComponentProps<typeof Menu.Positioner>, "sideOffset" | "align">) {
  return (
    <Menu.Portal>
      <Menu.Positioner sideOffset={sideOffset} align={align} className="z-50">
        <Menu.Popup
          data-slot="dropdown-menu-content"
          className={cn(
            "flex w-72 max-w-[calc(100vw-2rem)] origin-(--transform-origin) flex-col overflow-hidden rounded-xl border border-rule bg-panel text-ink shadow-lg transition-[opacity,transform] duration-150 data-[ending-style]:scale-95 data-[ending-style]:opacity-0 data-[starting-style]:scale-95 data-[starting-style]:opacity-0",
            className,
          )}
          {...props}
        />
      </Menu.Positioner>
    </Menu.Portal>
  );
}

function DropdownMenuItem({ className, ...props }: React.ComponentProps<typeof Menu.Item>) {
  return <Menu.Item data-slot="dropdown-menu-item" className={cn(ITEM, className)} {...props} />;
}

export { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem };

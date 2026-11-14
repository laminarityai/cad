import * as React from "react";
import { useRef, useState } from "react";
import { Menu } from "@base-ui/react/menu";
import { cn } from "@/lib/utils";

const DropdownMenu = Menu.Root;
const DropdownMenuTrigger = Menu.Trigger;

const ITEM = "flex cursor-default flex-col gap-0.5 border-t border-rule-2 px-3 py-2.5 text-left outline-none first:border-t-0 relative";

/*
 * The gliding hover is cut down from Beautiful UI's GlideMenu (https://www.beautifului.dev), MIT,
 * Copyright (c) 2026 Shane Levine. One layer slides to the hovered or keyboard-highlighted item.
 * The items stay base-ui's, so its keyboard handling is untouched.
 */
function Glide({ children }: { children: React.ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const [at, setAt] = useState<{ top: number; height: number } | null>(null);
  const [shown, setShown] = useState(false);
  const moveTo = (target: EventTarget | null) => {
    const holder = box.current;
    const row = target instanceof Element ? target.closest('[data-slot="dropdown-menu-item"]') : null;
    if (!holder || !(row instanceof HTMLElement) || !holder.contains(row)) return;
    setAt({ top: row.offsetTop, height: row.offsetHeight });
    setShown(true);
  };
  return (
    <div
      ref={box}
      data-glide
      className="relative flex flex-col"
      onMouseOver={(event) => {
        moveTo(event.target);
      }}
      onMouseLeave={() => {
        setShown(false);
      }}
      onFocusCapture={(event) => {
        moveTo(event.target);
      }}
      onBlurCapture={(event) => {
        if (!(event.relatedTarget instanceof Node && box.current?.contains(event.relatedTarget))) setShown(false);
      }}
    >
      <span
        aria-hidden
        data-glide-layer
        data-shown={shown && at ? "" : undefined}
        className="pointer-events-none absolute inset-x-0 bg-muted opacity-0 transition-[top,height,opacity] duration-200 ease-[cubic-bezier(0.23,1,0.32,1)] data-[shown]:opacity-100 motion-reduce:transition-none"
        style={{ top: at?.top ?? 0, height: at?.height ?? 0 }}
      />
      {children}
    </div>
  );
}

function DropdownMenuContent({
  className,
  sideOffset = 6,
  align,
  children,
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
        >
          <Glide>{children}</Glide>
        </Menu.Popup>
      </Menu.Positioner>
    </Menu.Portal>
  );
}

function DropdownMenuItem({ className, ...props }: React.ComponentProps<typeof Menu.Item>) {
  return <Menu.Item data-slot="dropdown-menu-item" className={cn(ITEM, className)} {...props} />;
}

export { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem };

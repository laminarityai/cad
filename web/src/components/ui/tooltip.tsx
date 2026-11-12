import type { ReactElement } from "react";
import { Tooltip as Primitive } from "@base-ui/react/tooltip";

const TooltipProvider = Primitive.Provider;

/** Shows `label` when the child is hovered or focused. The child is the trigger and keeps its own
 * role and name. A disabled child gets no pointer events, so `onDisabled` hangs the tooltip on a
 * focusable span around it. */
function Tooltip(props: { label: string; children: ReactElement; onDisabled?: boolean }) {
  const { label, children, onDisabled = false } = props;
  return (
    <Primitive.Root>
      <Primitive.Trigger render={onDisabled ? <span tabIndex={0} className="inline-flex">{children}</span> : children} />
      <Primitive.Portal>
        <Primitive.Positioner sideOffset={6} className="z-50">
          <Primitive.Popup
            data-slot="tooltip-content"
            className="max-w-72 origin-(--transform-origin) rounded-md border border-rule bg-panel px-2.5 py-1 text-[13px] text-ink shadow-md transition-opacity duration-150 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0"
          >
            {label}
          </Primitive.Popup>
        </Primitive.Positioner>
      </Primitive.Portal>
    </Primitive.Root>
  );
}

export { Tooltip, TooltipProvider };

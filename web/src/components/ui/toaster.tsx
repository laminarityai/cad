import { Toaster as Primitive, toast } from "sonner";

/** Mount once. A toast says a failure that has no lasting place on screen. An error that belongs to a control stays next to it. */
function Toaster() {
  return (
    <Primitive
      position="bottom-right"
      toastOptions={{
        unstyled: true,
        classNames: {
          toast: "flex w-72 items-start gap-2 rounded-md border border-rule bg-panel px-3 py-2 text-[13px] text-fail shadow-md",
        },
      }}
    />
  );
}

export { Toaster, toast };

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center border px-1.5 py-0.5 font-mono text-[10.5px] font-semibold uppercase tracking-wider",
  {
    variants: {
      tone: {
        pass: "border-pass bg-pass-bg text-pass",
        fail: "border-fail bg-fail-bg text-fail",
        researched: "border-res bg-res-bg text-res",
        unknown: "border-dashed border-unk bg-unk-bg text-unk",
        pending: "border-dotted border-ink-3 bg-transparent text-ink-3",
        waiting: "border-wait bg-wait-bg text-wait",
        neutral: "border-border bg-transparent text-ink-2",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

function Badge({
  className,
  tone,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return (
    <span
      data-slot="badge"
      data-tone={tone ?? "neutral"}
      className={cn(badgeVariants({ tone }), className)}
      {...props}
    />
  );
}

export { Badge, badgeVariants };

import { ArrowUpRight, TextAlignStart } from "lucide-react";
import { cn } from "@/lib/utils";

/*
 * Cut down from Beautiful UI's Context Cards (https://www.beautifului.dev), MIT, Copyright (c)
 * 2026 Shane Levine. The staged fade-in and the sample chunks are left out. Each card shows only
 * what its caller passes.
 */

export function ContextCard({ title, quote, address, href, className }: { title: string; quote: string; address: string; href: string; className?: string }) {
  return (
    <div data-context-card className={cn("overflow-hidden rounded-xl border border-rule bg-panel", className)}>
      <div className="flex items-center gap-1.5 border-b border-rule-2 px-3 py-1.5 text-[13px] font-medium text-ink">
        <TextAlignStart aria-hidden className="size-3 shrink-0 text-ink-3" />
        <span className="truncate">{title}</span>
      </div>
      {quote === "" ? null : <p className="line-clamp-4 px-3 pt-2 text-[12.5px] leading-relaxed text-ink-2">{quote}</p>}
      <div className="px-3 pb-2.5 pt-2">
        <a
          href={href}
          target="_blank"
          rel="noreferrer"
          className="inline-flex h-6 max-w-full items-center gap-1 rounded-full border border-rule bg-panel-2 px-2 text-[12px] font-medium text-ink-2 transition-colors hover:bg-rule-2 hover:text-ink"
        >
          <span className="truncate">{address}</span>
          <ArrowUpRight aria-hidden className="size-3 shrink-0" />
        </a>
      </div>
    </div>
  );
}

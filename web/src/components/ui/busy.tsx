import { useEffect, useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/*
 * Cut down from Beautiful UI (https://www.beautifului.dev), MIT, Copyright (c) 2026 Shane Levine.
 * The licence text is beautiful-ui.LICENSE in this folder.
 */

const CHEVRON_DELAYS = [0, 90, 180, 90, 180, 270, 180, 270, 360];

function Grid({ className }: { className?: string }) {
  return (
    <span aria-hidden className={cn("grid shrink-0 grid-cols-[repeat(3,4px)] gap-[1.5px]", className)}>
      {CHEVRON_DELAYS.map((delay, at) => (
        <span key={at} data-busy-cell className="size-[4px] rounded-[1px] bg-ink" style={{ animationDelay: `${String(delay)}ms` }} />
      ))}
    </span>
  );
}

export function Shimmer({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span data-shimmer className={cn("busy-shimmer", className)}>
      {children}
    </span>
  );
}

const SPINNER_RING = 2 * Math.PI * 8;

export function Spinner({ className }: { className?: string }) {
  return (
    <svg aria-hidden data-spinner viewBox="0 0 20 20" className={cn("size-[18px] shrink-0 motion-safe:animate-spin", className)}>
      <circle cx="10" cy="10" r="8" fill="none" stroke="var(--rule)" strokeWidth="2" />
      <circle cx="10" cy="10" r="8" fill="none" stroke="var(--ink-3)" strokeWidth="2" strokeLinecap="round" strokeDasharray={`${String(SPINNER_RING * 0.28)} ${String(SPINNER_RING * 0.72)}`} />
    </svg>
  );
}

function useSeconds(since: number | null): number {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (since === null) return;
    const tick = setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      clearInterval(tick);
    };
  }, [since]);
  return since === null ? 0 : Math.max(0, Math.floor((now - since) / 1000));
}

const clock = (seconds: number) => (seconds < 60 ? `${String(seconds)}s` : `${String(Math.floor(seconds / 60))}m ${String(seconds % 60)}s`);

export function Loading({ label, since = null, size = "regular", className }: { label: string; since?: number | null; size?: "regular" | "small"; className?: string }) {
  const seconds = useSeconds(since);
  return (
    <div role="status" data-loading className={cn("flex w-fit items-center gap-2.5", size === "small" ? "text-[13px]" : "text-[14px]", className)}>
      <Grid />
      <Shimmer className="font-medium">{label}</Shimmer>
      {since === null ? null : (
        <span aria-hidden className="font-mono text-[12px] tabular-nums text-ink-3">
          {clock(seconds)}
        </span>
      )}
    </div>
  );
}

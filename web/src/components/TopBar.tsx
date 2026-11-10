import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export function TopBar({ trail, children }: { trail?: ReactNode; children?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-border bg-panel px-4 py-2.5">
      <Link to="/" className="font-mono font-semibold tracking-wide">
        cad<b className="text-accent">.</b>
      </Link>
      {trail ? <nav className="font-mono text-xs text-ink-2">{trail}</nav> : null}
      <div className="min-w-0 flex-1 basis-64">{children}</div>
    </header>
  );
}

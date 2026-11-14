import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";

/*
 * Cut down from Beautiful UI's Code Block (https://www.beautifului.dev), MIT, Copyright (c) 2026
 * Shane Levine. The licence text is beautiful-ui.LICENSE in this folder. The Diff view and the
 * token colouring are left out.
 */

export function CodeBlock({ code, language, className }: { code: string; language?: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const reset = setTimeout(() => {
      setCopied(false);
    }, 1500);
    return () => {
      clearTimeout(reset);
    };
  }, [copied]);
  const copy = () => {
    navigator.clipboard.writeText(code).then(
      () => {
        setCopied(true);
      },
      () => undefined,
    );
  };
  return (
    <div data-code-block className={cn("w-full overflow-hidden rounded-xl border border-rule bg-panel-2", className)}>
      <div className="flex h-9 items-center gap-2 border-b border-rule px-3 text-[12.5px]">
        <span className="truncate font-mono text-ink-3">{language ?? "code"}</span>
        <button
          type="button"
          aria-label="Copy code"
          onClick={copy}
          className={cn("-mr-1 ml-auto flex h-6 items-center gap-1 rounded-md px-1.5 text-[12px] font-medium transition-colors hover:bg-rule-2", copied ? "text-pass" : "text-ink-3 hover:text-ink")}
        >
          {copied ? <Check aria-hidden className="size-3" /> : <Copy aria-hidden className="size-3" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto py-3 font-mono text-[12.5px] leading-[1.65] text-ink-2">
        <code className="block min-w-fit">
          {code.split("\n").map((line, at) => (
            <span key={at} className="grid grid-cols-[2.5rem_1fr] pr-3">
              <span aria-hidden data-line-number className="select-none pr-3 text-right text-[11px] text-ink-3">
                {at + 1}
              </span>
              <span className="whitespace-pre">{line === "" ? "\n" : line}</span>
            </span>
          ))}
        </code>
      </pre>
    </div>
  );
}

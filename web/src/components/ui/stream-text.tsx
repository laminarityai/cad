import { cn } from "@/lib/utils";

/*
 * Cut down from Beautiful UI's Streaming Text (https://www.beautifului.dev), MIT, Copyright (c)
 * 2026 Shane Levine. The word timer, the sample citations and the follow-ups are left out. A
 * word fades in from blur when the server's text first reaches it, and no timer paces it.
 */

/** The text, split at spaces. A word keeps its place by its index, so only a newly arrived word plays the entrance. */
export function StreamWords({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\s+)/).map((part, at) =>
        part === "" || /^\s+$/.test(part) ? (
          part
        ) : (
          <span key={at} data-stream-word className="stream-word">
            {part}
          </span>
        ),
      )}
    </>
  );
}

export function StreamCaret({ className }: { className?: string }) {
  return <span aria-hidden data-stream-caret className={cn("stream-caret ml-0.5 inline-block h-3.5 w-0.5 translate-y-0.5 rounded-full bg-ink", className)} />;
}

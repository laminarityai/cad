import { cn } from "@/lib/utils";
import { reasonText, isStopKind } from "@/mode/run";
import type { Line } from "./state";

const WHO = "mb-0.5 font-mono text-[10px] uppercase tracking-widest text-ink-3";

function ToolLine({ line }: { line: Extract<Line, { kind: "tool" }> }) {
  const state = line.result === null ? "running" : line.result.isError ? "refused" : "done";
  return (
    <details data-line="tool" data-state={state} className="font-mono text-[11.5px] text-ink-2">
      <summary className="cursor-pointer border-t border-dashed border-rule pt-1.5">
        {line.name}
        {" · "}
        <span className={cn(state === "refused" && "text-fail")}>{state}</span>
        {line.result?.isError ? <span className="text-fail">{` · ${line.result.text}`}</span> : null}
      </summary>
      <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words pt-1">
        {JSON.stringify(line.input, null, 1)}
        {line.result === null ? "" : `\n→ ${line.result.text}`}
      </pre>
    </details>
  );
}

export function ChatLine({ line }: { line: Line }) {
  switch (line.kind) {
    case "user":
      return (
        <div data-line="user">
          <p className={WHO}>You</p>
          <p className="inline-block whitespace-pre-wrap break-words bg-ink px-2.5 py-2 text-background">{line.text}</p>
        </div>
      );
    case "agent":
      return (
        <div data-line="agent">
          <p className={WHO}>Agent</p>
          <p className="whitespace-pre-wrap break-words border-l-2 border-accent pl-2.5">{line.text}</p>
        </div>
      );
    case "driver":
      return <p data-line="driver" className="border-t border-dashed border-rule pt-1.5 font-mono text-[11.5px] text-ink-2">{line.text}</p>;
    case "tool":
      return <ToolLine line={line} />;
    case "stop_report":
      return (
        <div data-line="stop_report" className="border border-border bg-panel-2 px-2.5 py-2">
          <p className={WHO}>Auto stopped · {isStopKind(line.reason) ? reasonText(line.reason) : line.reason}</p>
          <p className="whitespace-pre-wrap break-words text-xs">{line.report}</p>
        </div>
      );
    case "failed":
      return (
        <p data-line="failed" role="alert" className="border-l-2 border-fail pl-2.5 text-fail">
          {line.message}
        </p>
      );
  }
}

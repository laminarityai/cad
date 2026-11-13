import { Check, Crosshair, Paperclip, SendHorizontal, X } from "lucide-react";
import { useEffect, useReducer, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useServices } from "@/app/context";
import { Refused } from "@/api/client";
import { chatReducer, chatStart, type Line } from "@/features/chat/state";
import { Loading } from "@/components/ui/busy";
import { ToolChips, type ToolRow } from "@/components/ui/tool-chips";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { isStopKind, reasonText } from "@/features/auto/run";
import { nowLabel, workingLabel, type Working } from "@/features/chat/working";
import { buildOf } from "@/features/chat/built";
import { Markdown } from "./Markdown";

export const DOING: Record<string, string> = {
  build_variant: "built",
  auto_revise: "built",
  score_variant: "checked",
  propose_requirements: "wrote requirements",
  propose_context_part: "added a part to fit",
  create_brief: "started a part",
  ask_to_confirm: "asked you",
  submit_research: "researched",
  write_check: "wrote a check",
  search_knowledge: "looked it up",
};

const WORKED = "worked";
const BUILD_UNREAD = "build finished";

export const CHANGES_PAGE: ReadonlySet<string> = new Set(["build_variant", "auto_revise", "score_variant", "propose_requirements", "propose_context_part", "create_brief", "ask_to_confirm"]);

export type Change = { kind: "tool"; name: string } | { kind: "turn_ended" } | { kind: "stop_report" };

export function useProjectChat(conversationId: string | null, onChange?: (change: Change) => void) {
  const { chat } = useServices();
  const [state, dispatch] = useReducer(chatReducer, conversationId, chatStart);
  const heard = useRef(onChange);
  useEffect(() => {
    heard.current = onChange;
  });
  useEffect(() => {
    if (conversationId === null) return;
    dispatch({ type: "open", conversationId });
    const names = new Map<string, string>();
    return chat.follow(conversationId, 0, {
      onEvent: (seq, event) => {
        dispatch({ type: "event", seq, event });
        if (event.kind === "tool_call") names.set(event.call_id, event.name);
        if (event.kind === "tool_result")
          heard.current?.({
            kind: "tool",
            name: names.get(event.call_id) ?? "",
          });
        if (event.kind === "stop_report") heard.current?.({ kind: "stop_report" });
        if (event.kind === "turn_ended") heard.current?.({ kind: "turn_ended" });
      },
      onLink: (link) => {
        dispatch({ type: "link", link });
      },
    });
  }, [chat, conversationId]);
  return state;
}

type Shown = { kind: "line"; line: Line } | { kind: "activity"; key: number; lines: Call[] };

function grouped(lines: readonly Line[]): Shown[] {
  const out: Shown[] = [];
  for (const line of lines) {
    const last = out[out.length - 1];
    if (line.kind === "tool") {
      if (last?.kind === "activity") last.lines.push(line);
      else out.push({ kind: "activity", key: line.seq, lines: [line] });
    } else out.push({ kind: "line", line });
  }
  return out;
}

type Call = Extract<Line, { kind: "tool" }>;

function doneWord(call: Pick<Call, "name" | "result">): string {
  if (call.result !== null && buildOf(call.name, call.result.text) === "unread") return BUILD_UNREAD;
  return DOING[call.name] ?? WORKED;
}

export function activityText(words: readonly string[]): string {
  const counts = new Map<string, number>();
  for (const word of words) counts.set(word, (counts.get(word) ?? 0) + 1);
  const text = [...counts.entries()].map(([word, n]) => (n > 1 && (word === "built" || word === "checked") ? `${word} ${String(n)}` : word)).join(", ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

const CHIP: Record<string, (input: Record<string, unknown>) => string | null> = {
  build_variant: (input) => (typeof input.label === "string" ? input.label : typeof input.slot === "number" ? `Option ${String(input.slot)}` : null),
  auto_revise: (input) => (typeof input.slot === "number" ? `Option ${String(input.slot)}` : null),
};

const SHORT = 80;

function detailOf(input: Record<string, unknown>): string[] {
  return Object.entries(input).flatMap(([key, value]) => {
    if (key.endsWith("_id") || key === "code") return [];
    if (typeof value === "number" || (typeof value === "string" && value.length <= SHORT)) return [`${key}: ${String(value)}`];
    return [];
  });
}

/** `live` while the turn runs, `stalled` while it runs but the stream dropped, `over` once it ended. */
type Phase = "live" | "stalled" | "over";

function statusesOf(lines: readonly Call[], phase: Phase): ToolRow["status"][] {
  const first = lines.findIndex((one) => one.result === null);
  return lines.map((one, at) => {
    if (one.result !== null) return one.result.isError ? "refused" : buildOf(one.name, one.result.text) === "failed" ? "failed" : "done";
    if (phase === "over") return "unfinished";
    if (phase === "stalled") return "unanswered";
    return at === first ? "running" : "queued";
  });
}

const lower = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

const builds = (n: number) => `${String(n)} ${n === 1 ? "build" : "builds"}`;

function summaryText(lines: readonly Call[], phase: Phase): string {
  const statuses = statusesOf(lines, phase);
  const count = (status: ToolRow["status"]) => statuses.filter((one) => one === status).length;
  const done = lines.filter((_, at) => statuses[at] === "done").map(doneWord);
  const running = lines.find((_, at) => statuses[at] === "running");
  const parts = [
    ...(done.length > 0 ? [activityText(done)] : []),
    ...(count("failed") > 0 ? [`${builds(count("failed"))} failed`] : []),
    ...(count("refused") > 0 ? [`${String(count("refused"))} refused`] : []),
    ...(count("unanswered") > 0 ? [`${String(count("unanswered"))} with no answer yet`] : []),
    ...(count("unfinished") > 0 ? [`${String(count("unfinished"))} did not finish`] : []),
    ...(running ? [nowLabel(running.name)] : []),
  ];
  const text = parts.map(lower).join(", ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function labelOf(line: Call, status: ToolRow["status"]): string {
  if (status === "failed") return "Build failed";
  return status === "done" || status === "refused" ? activityText([doneWord(line)]) : nowLabel(line.name);
}

function Activity({ lines, phase }: { lines: Call[]; phase: Phase }) {
  const statuses = statusesOf(lines, phase);
  const rows = lines.map((line, at): ToolRow => {
    const status = statuses[at] ?? "done";
    return {
      key: line.seq,
      label: labelOf(line, status),
      chip: CHIP[line.name]?.(line.input) ?? null,
      status,
      detail: detailOf(line.input),
    };
  });
  return <ToolChips summary={summaryText(lines, phase)} rows={rows} live={phase === "live"} />;
}

export function driverText(text: string): string | null {
  const [, confirmed, declined] = /confirmed (\d+) and declined (\d+)/.exec(text) ?? [];
  if (confirmed === undefined || declined === undefined) return null;
  return Number(declined) > 0 ? `You confirmed ${confirmed}, declined ${declined}` : `You confirmed ${confirmed}`;
}

function Said({ line }: { line: Line }) {
  switch (line.kind) {
    case "user":
      return (
        <div data-said="user" className="flex flex-col items-end gap-1">
          <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-accent/15 px-3.5 py-2 text-[15px]">{line.text}</p>
          {line.selection === null ? null : (
            <span data-said-selection className="flex items-center gap-1 rounded-full border border-rule px-2.5 py-0.5 text-[13px] text-ink-2">
              <Crosshair className="size-3.5" /> Pointed at {line.selection}
            </span>
          )}
        </div>
      );
    case "driver": {
      const said = driverText(line.text);
      if (said === null) return null;
      return (
        <p data-said="driver" className="flex items-center gap-1.5 text-[14px] text-pass">
          <Check className="size-4" /> {said}
        </p>
      );
    }
    case "agent":
      return (
        <div data-said="agent" className="text-[15px] leading-relaxed">
          <Markdown text={line.text} />
        </div>
      );
    case "stop_report":
      return (
        <div data-said="stop_report" className="rounded-xl border border-rule px-3.5 py-2 text-[15px]">
          <p className="text-[13px] text-ink-3">Auto stopped · {isStopKind(line.reason) ? reasonText(line.reason) : line.reason}</p>
          <Markdown text={line.report} />
        </div>
      );
    case "failed":
      return <p className="text-[15px] text-fail">{line.message}</p>;
    default:
      return null;
  }
}

const BUSY = "The agent is still answering. Send this again when it is done.";

export interface PointedAt {
  label: string;
  onRemove: () => void;
}

export function Composer(props: { placeholder: string; onSend: (text: string) => Promise<void>; big?: boolean; selection?: PointedAt | null }) {
  const { placeholder, onSend, big, selection } = props;
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const submit = async () => {
    if (text.trim() === "" || busy) return;
    setBusy(true);
    setProblem(null);
    try {
      await onSend(text.trim());
      setText("");
    } catch (error) {
      setProblem(error instanceof Refused && error.status === 409 ? BUSY : error instanceof Error ? error.message : "The message was not sent.");
    } finally {
      setBusy(false);
    }
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  };
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
      className={cn("rounded-2xl border border-rule bg-panel-2 focus-within:border-accent", big ? "p-3" : "p-2")}
    >
      {selection ? (
        <span data-selection-chip className="m-1 inline-flex items-center gap-1.5 rounded-full border border-rule bg-panel py-0.5 pl-2.5 pr-1 text-[14px]">
          <Crosshair className="size-3.5 text-accent" />
          {selection.label}
          <button type="button" aria-label="Remove selection" onClick={selection.onRemove} className="rounded-full p-0.5 text-ink-3 hover:text-ink">
            <X className="size-3.5" />
          </button>
        </span>
      ) : null}
      <textarea
        aria-label="Message"
        value={text}
        rows={big ? 3 : 2}
        placeholder={placeholder}
        onChange={(event) => {
          setText(event.target.value);
        }}
        onKeyDown={onKeyDown}
        className={cn("w-full resize-none bg-transparent px-2 py-1 outline-none placeholder:text-ink-3", big ? "text-[17px]" : "text-[15px]")}
      />
      {problem ? (
        <p role="alert" className="px-2 pb-1 text-[14px] text-fail">
          {problem}
        </p>
      ) : null}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Tooltip label="Coming soon" onDisabled>
            <button type="button" disabled aria-label="Attach files" className="rounded-lg p-1.5 text-ink-3 disabled:cursor-not-allowed">
              <Paperclip className="size-[18px]" />
            </button>
          </Tooltip>
        </div>
        <button
          type="submit"
          disabled={busy || text.trim() === ""}
          aria-label="Send"
          className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-[15px] font-medium text-accent-ink disabled:opacity-40"
        >
          <SendHorizontal className="size-4" /> Send
        </button>
      </div>
    </form>
  );
}

const STALLED = "The server is not answering. The page is reconnecting.";

export function ChatPane(props: { lines: readonly Line[]; working: Working | null; stalled?: boolean; since?: number | null; card: ReactNode; composer: ReactNode; status?: ReactNode }) {
  const { lines, working, stalled = false, since = null, card, composer, status } = props;
  const phase: Phase = working !== null ? "live" : stalled ? "stalled" : "over";
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [lines, card]);
  return (
    <section aria-label="Chat" aria-busy={working !== null} className="flex h-full min-h-0 flex-col">
      <div role="log" className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {grouped(lines).map((one, at, all) => (one.kind === "activity" ? <Activity key={`a${String(one.key)}`} lines={one.lines} phase={at === all.length - 1 ? phase : "over"} /> : <Said key={one.line.seq} line={one.line} />))}
        {working === null ? null : <Loading label={workingLabel(working)} since={since} />}
        {stalled ? (
          <p role="status" data-stalled className="text-[14px] text-ink-2">
            {STALLED}
          </p>
        ) : null}
        {card}
        <div ref={end} />
      </div>
      <div className="space-y-2 border-t border-rule-2 p-3">
        {status}
        {composer}
      </div>
    </section>
  );
}

/* Throwaway prototype: the project's one chat. Agent text is Markdown. Tool calls fold into one
 * quiet line. What waits on the person is a card the page draws, never agent text. */
import { Box, Check, ChevronDown, Crosshair, Paperclip, Pencil, SendHorizontal, Undo2, X } from "lucide-react";
import { useEffect, useReducer, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { useServices } from "@/app/context";
import { chatReducer, chatStart, type Line } from "@/chat/state";
import { cn } from "@/lib/utils";
import { Markdown } from "./Markdown";
import type { Ask, Highlight } from "./model";

const DOING: Record<string, string> = {
  build_variant: "built",
  auto_revise: "built",
  score_variant: "checked",
  propose_requirements: "wrote requirements",
  propose_context_part: "added a part to fit",
  create_brief: "started a part",
  ask_to_confirm: "asked you",
  submit_research: "researched",
  search_knowledge: "looked it up",
};

export function useProjectChat(conversationId: string | null) {
  const { chat } = useServices();
  const [state, dispatch] = useReducer(chatReducer, conversationId, chatStart);
  useEffect(() => {
    if (conversationId === null) return;
    return chat.follow(conversationId, 0, {
      onEvent: (seq, event) => {
        dispatch({ type: "event", seq, event });
      },
      onLink: (link) => {
        dispatch({ type: "link", link });
      },
    });
  }, [chat, conversationId]);
  return state;
}

type Shown = { kind: "line"; line: Line } | { kind: "activity"; key: number; lines: Extract<Line, { kind: "tool" }>[] };

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

function Activity({ lines }: { lines: Extract<Line, { kind: "tool" }>[] }) {
  const [open, setOpen] = useState(false);
  const counts = new Map<string, number>();
  for (const one of lines) {
    const word = DOING[one.name];
    if (word) counts.set(word, (counts.get(word) ?? 0) + 1);
  }
  const words = [...counts.entries()].map(([word, n]) => (n > 1 && (word === "built" || word === "checked") ? `${word} ${String(n)}` : word));
  const running = lines.some((one) => one.result === null);
  const text = words.length > 0 ? words.join(", ") : "looked things up";
  return (
    <div data-activity className="text-[13px] text-ink-3">
      <button
        type="button"
        onClick={() => {
          setOpen((was) => !was);
        }}
        className="flex items-center gap-1.5"
      >
        <span className={cn("size-1.5 rounded-full", running ? "bg-wait motion-safe:animate-pulse" : "bg-ink-3")} />
        {text.charAt(0).toUpperCase() + text.slice(1)}
        <ChevronDown className={cn("size-3.5", open && "rotate-180")} />
      </button>
      {open ? (
        <ul className="mt-1 space-y-0.5 pl-3 font-mono text-[12px]">
          {lines.map((one) => (
            <li key={one.seq}>
              {one.name} {one.result?.isError ? "· refused" : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function Said({ line, pointed }: { line: Line; pointed?: string }) {
  switch (line.kind) {
    case "user":
      return (
        <div data-said="user" className="flex flex-col items-end gap-1">
          {pointed ? (
            <span className="flex items-center gap-1.5 rounded-full bg-accent/15 px-2.5 py-0.5 text-[13px] text-accent">
              <Crosshair className="size-3.5" /> {pointed}
            </span>
          ) : null}
          <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-accent/15 px-3.5 py-2 text-[15px]">{line.text}</p>
        </div>
      );
    case "driver":
      return (
        <p data-said="driver" className="flex items-center gap-1.5 text-[14px] text-pass">
          <Check className="size-4" /> {line.text}
        </p>
      );
    case "agent":
      return (
        <div data-said="agent" className="text-[15px] leading-relaxed">
          <Markdown text={line.text} />
        </div>
      );
    case "stop_report":
      return <div className="rounded-xl border border-rule px-3.5 py-2 text-[15px]"><Markdown text={line.report} /></div>;
    case "failed":
      return <p className="text-[15px] text-fail">{line.message}</p>;
    default:
      return null;
  }
}

type Answer = { kind: "yes" } | { kind: "no" } | { kind: "edit"; text: string };

/** One card for everything waiting in the project. Each row says what it is and the words it came
 * from. Every row starts as yes; the person can edit or decline one. MOCK: it posts nothing. */
export function ConfirmCard({ asks, onDone }: { asks: Ask[]; onDone: (yes: number, no: number) => void }) {
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const [editing, setEditing] = useState<string | null>(null);
  const rows = asks.flatMap((ask) => ask.rows.map((row) => ({ ...row, brief: ask.briefTitle })));
  if (rows.length === 0) return null;
  const answerOf = (id: string): Answer => answers[id] ?? { kind: "yes" };
  const put = (id: string, answer: Answer) => {
    setAnswers((now) => ({ ...now, [id]: answer }));
  };
  const yes = rows.filter((row) => answerOf(row.id).kind !== "no").length;
  return (
    <section data-confirm-card aria-label="Confirm before I build" className="overflow-hidden rounded-2xl border border-wait/60 bg-panel-2">
      <header className="flex items-baseline justify-between border-b border-rule-2 bg-wait-bg/60 px-4 py-2.5">
        <h3 className="text-[15px] font-semibold">Confirm before I build</h3>
        <span className="text-[13px] text-ink-2">{asks.map((ask) => ask.briefTitle).join(", ")}</span>
      </header>
      <ul>
        {rows.map((row) => {
          const answer = answerOf(row.id);
          const no = answer.kind === "no";
          return (
            <li key={row.id} data-ask-row={answer.kind} className={cn("flex gap-3 border-b border-rule-2 px-4 py-2.5 last:border-b-0", no && "opacity-50")}>
              {row.kind === "part" ? <Box className="mt-0.5 size-[18px] shrink-0 text-ink-2" /> : <Check className={cn("mt-0.5 size-[18px] shrink-0", no ? "text-ink-3" : "text-pass")} />}
              <div className="min-w-0 flex-1">
                {editing === row.id ? (
                  <input
                    autoFocus
                    defaultValue={answer.kind === "edit" ? answer.text : row.text}
                    onBlur={(event) => {
                      put(row.id, event.target.value === row.text ? { kind: "yes" } : { kind: "edit", text: event.target.value });
                      setEditing(null);
                    }}
                    className="w-full rounded-md border border-accent bg-panel px-2 py-1 text-[15px] outline-none"
                  />
                ) : (
                  <p className={cn("text-[15px] leading-snug", no && "line-through")}>
                    {row.kind === "part" ? <span className="text-ink-2">Must fit: </span> : null}
                    {answer.kind === "edit" ? answer.text : row.text}
                    {answer.kind === "edit" ? <span className="ml-1.5 text-[12px] text-accent">edited</span> : null}
                  </p>
                )}
                <p className="mt-0.5 text-[13px] text-ink-3">
                  from <mark className="rounded bg-wait-bg px-1 text-ink-2">“{row.quote}”</mark>
                </p>
              </div>
              <div className="flex shrink-0 items-start gap-1">
                <button type="button" aria-label="Edit" onClick={() => { setEditing(row.id); }} className="rounded-md p-1 text-ink-3 hover:bg-panel hover:text-ink">
                  <Pencil className="size-4" />
                </button>
                <button
                  type="button"
                  aria-label={no ? "Keep" : "Decline"}
                  onClick={() => {
                    put(row.id, no ? { kind: "yes" } : { kind: "no" });
                  }}
                  className="rounded-md p-1 text-ink-3 hover:bg-panel hover:text-ink"
                >
                  {no ? <Undo2 className="size-4" /> : <X className="size-4" />}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      <footer className="flex items-center gap-3 px-4 py-3">
        <button
          type="button"
          data-confirm
          onClick={() => {
            onDone(yes, rows.length - yes);
          }}
          className="rounded-lg bg-accent px-4 py-2 text-[15px] font-semibold text-accent-ink hover:opacity-90"
        >
          Confirm {yes === rows.length ? "all" : String(yes)}
        </button>
        <span className="text-[13px] text-ink-3">Only you can confirm.</span>
      </footer>
    </section>
  );
}

export function Composer(props: {
  placeholder: string;
  highlight: Highlight | null;
  onClearHighlight: () => void;
  onSend: (text: string) => Promise<void>;
  onAttach: (files: File[]) => void;
  big?: boolean;
  initial?: string;
}) {
  const { placeholder, highlight, onClearHighlight, onSend, onAttach, big, initial } = props;
  const [text, setText] = useState(initial ?? "");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const submit = async () => {
    if (text.trim() === "" || busy) return;
    setBusy(true);
    await onSend(text.trim());
    setBusy(false);
    setText("");
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
      {highlight ? (
        <div data-highlight-chip className="mb-2 flex items-center gap-2 rounded-lg bg-accent/15 px-2.5 py-1.5 text-[14px]">
          <Crosshair className="size-4 text-accent" />
          <span className="truncate">{highlight.label}</span>
          <button type="button" aria-label="Clear highlight" onClick={onClearHighlight} className="ml-auto text-ink-3 hover:text-ink">
            <X className="size-4" />
          </button>
        </div>
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
      <div className="flex items-center justify-between">
        <button type="button" onClick={() => input.current?.click()} aria-label="Attach files" className="rounded-lg p-1.5 text-ink-2 hover:bg-panel">
          <Paperclip className="size-[18px]" />
        </button>
        <input
          ref={input}
          type="file"
          multiple
          hidden
          onChange={(event) => {
            onAttach([...(event.target.files ?? [])]);
          }}
        />
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

export function ChatPane(props: {
  lines: readonly Line[];
  pointed: Record<number, string>;
  running: boolean;
  card: ReactNode;
  composer: ReactNode;
  notice: string | null;
}) {
  const { lines, pointed, running, card, composer, notice } = props;
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [lines, card, notice]);
  return (
    <section aria-label="Chat" className="flex h-full min-h-0 flex-col">
      <div role="log" className="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {grouped(lines).map((one) => (one.kind === "activity" ? <Activity key={`a${String(one.key)}`} lines={one.lines} /> : <Said key={one.line.seq} line={one.line} pointed={pointed[one.line.seq]} />))}
        {running ? <p className="text-[14px] text-ink-3">Working…</p> : null}
        {card}
        {notice ? <p className="rounded-lg bg-panel-2 px-3 py-2 text-[14px] text-ink-2">{notice}</p> : null}
        <div ref={end} />
      </div>
      <div className="border-t border-rule-2 p-3">{composer}</div>
    </section>
  );
}

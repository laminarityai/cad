import { Undo2, X } from "lucide-react";
import { useState } from "react";
import { useServices } from "@/app/context";
import type { ConfirmationCard } from "@/api/types";
import { cn } from "@/lib/utils";

type Card = ConfirmationCard & { snapshot: string };

export function formOf(card: Card, answer: "confirm" | "decline", declined: ReadonlySet<number>, edits: Readonly<Record<string, string>>, note: string): URLSearchParams {
  const form = new URLSearchParams({ snapshot: card.snapshot, answer, note });
  if (answer === "decline") return form;
  card.items.forEach((item, at) => {
    if (declined.has(at)) {
      form.set(`decline-${String(at)}`, "decline");
      return;
    }
    for (const row of item.rows) {
      const typed = row.editable ? edits[`${String(at)}-${row.editable.row}`]?.trim() : undefined;
      if (row.editable && typed) form.set(`edit-${String(at)}-${row.editable.row}`, typed);
    }
  });
  return form;
}

export function ConfirmCard({ projectId, card, onAnswered }: { projectId: string; card: Card; onAnswered: (recorded: boolean) => void }) {
  const { api } = useServices();
  const [declined, setDeclined] = useState<ReadonlySet<number>>(new Set());
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [note, setNote] = useState("");
  const [declining, setDeclining] = useState(false);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const several = card.items.length > 1;
  const toggle = (at: number) => {
    setDeclined((now) => {
      const next = new Set(now);
      if (!next.delete(at)) next.add(at);
      return next;
    });
  };
  const send = async (answer: "confirm" | "decline") => {
    setBusy(true);
    setProblem(null);
    try {
      const said = await api.answer(projectId, formOf(card, answer, declined, edits, note));
      if (said.status === 200 || said.status === 409) onAnswered(said.status === 200);
      else setProblem(said.text || `The answer was refused (${String(said.status)}).`);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "The answer was not sent.");
    } finally {
      setBusy(false);
    }
  };
  const asksNote = declining || declined.size > 0;
  return (
    <section data-confirm-card aria-label="Confirm your targets" className="overflow-hidden rounded-2xl border border-wait/60 bg-panel-2">
      <header className="border-b border-rule-2 bg-wait-bg/60 px-4 py-2.5">
        <h3 className="text-[15px] font-semibold">Confirm your targets</h3>
      </header>
      {card.items.map((item, at) => {
        const no = declined.has(at);
        return (
          <div key={`${item.kind}:${item.brief_id}:${String(at)}`} data-item={at} className={cn("border-b border-rule-2 px-4 py-3", no && "opacity-60")}>
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <h4 className="text-[14px] font-medium text-ink-2">{item.title}</h4>
                <p className="line-clamp-2 text-[13px] text-ink-3">“{item.brief_text}”</p>
              </div>
              {several ? (
                <button
                  type="button"
                  aria-pressed={no}
                  onClick={() => {
                    toggle(at);
                  }}
                  className="flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[13px] text-ink-2 hover:bg-panel"
                >
                  {no ? <Undo2 className="size-4" /> : <X className="size-4" />} {no ? "Keep" : "Decline"}
                </button>
              ) : null}
            </div>
            <ul className="mt-2 space-y-2">
              {item.rows.map((row, index) => {
                const key = row.editable ? `${String(at)}-${row.editable.row}` : null;
                return (
                  <li key={index} data-ask-row className="text-[15px] leading-snug">
                    <p className={cn(no && "line-through")}>{row.headline}</p>
                    {row.quote ? (
                      <p className="mt-0.5 text-[13px] text-ink-3">
                        from {row.source === "your words" ? null : `${row.source}: `}
                        <mark className="rounded bg-wait-bg px-1 text-ink-2">“{row.quote}”</mark>
                      </p>
                    ) : null}
                    {row.note ? <p className="mt-0.5 text-[13px] text-ink-2">{row.note}</p> : null}
                    {row.editable && key && !no ? (
                      <input
                        aria-label={`New value for ${row.headline}`}
                        inputMode="text"
                        placeholder={row.editable.placeholder}
                        value={edits[key] ?? ""}
                        onChange={(event) => {
                          setEdits((now) => ({
                            ...now,
                            [key]: event.target.value,
                          }));
                        }}
                        className="mt-1 w-56 max-w-full rounded-md border border-rule bg-panel px-2 py-1 text-[14px] outline-none focus:border-accent"
                      />
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
      {asksNote ? (
        <div className="border-b border-rule-2 px-4 py-3">
          <textarea
            aria-label="Note for the agent"
            value={note}
            rows={2}
            placeholder="What should change? The agent reads this."
            onChange={(event) => {
              setNote(event.target.value);
            }}
            className="w-full resize-none rounded-md border border-rule bg-panel px-2 py-1 text-[14px] outline-none focus:border-accent"
          />
        </div>
      ) : null}
      <footer className="flex flex-wrap items-center gap-3 px-4 py-3">
        <button
          type="button"
          data-confirm
          disabled={busy}
          onClick={() => void send("confirm")}
          className="rounded-lg bg-accent px-4 py-2 text-[15px] font-semibold text-accent-ink hover:opacity-90 disabled:opacity-50"
        >
          {declined.size > 0 ? `Confirm ${String(card.items.length - declined.size)}, decline ${String(declined.size)}` : "Confirm"}
        </button>
        <button
          type="button"
          data-decline
          disabled={busy}
          onClick={() => {
            if (declining) void send("decline");
            else setDeclining(true);
          }}
          className="rounded-lg border border-rule px-3 py-2 text-[15px] hover:bg-panel disabled:opacity-50"
        >
          {declining ? "Send decline" : several ? "Decline all" : "Decline"}
        </button>
        <span className="text-[13px] text-ink-3">Only you can confirm.</span>
        {problem ? (
          <p role="alert" className="w-full text-[14px] text-fail">
            {problem}
          </p>
        ) : null}
      </footer>
    </section>
  );
}

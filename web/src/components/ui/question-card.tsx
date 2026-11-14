import { useState, type KeyboardEvent } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/*
 * Cut down from Beautiful UI's Approval Card (https://www.beautifului.dev), MIT, Copyright (c) 2026
 * Shane Levine.
 */

export interface CardQuestion {
  question: string;
  default: string;
  why: string;
  suggestions: readonly string[];
}

/** One question at a time, each with its suggested answers, a typed answer and its default. Skip
 * sends what is answered so far, and Continue moves on, sending the answers on the last question. */
export function QuestionCard({ questions, onSend }: { questions: readonly CardQuestion[]; onSend: (answers: readonly string[]) => Promise<void> }) {
  const [at, setAt] = useState(0);
  const [answers, setAnswers] = useState<readonly string[]>(() => questions.map(() => ""));
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const shown = questions[at];
  if (shown === undefined) return null;
  const last = at === questions.length - 1;
  const answer = answers[at] ?? "";
  const answerWith = (text: string) => {
    setAnswers((held) => held.map((one, n) => (n === at ? text : one)));
  };
  const send = async () => {
    if (busy) return;
    setBusy(true);
    setProblem(null);
    try {
      await onSend(answers);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "The answers were not sent.");
    } finally {
      setBusy(false);
    }
  };
  const next = () => {
    if (last) void send();
    else setAt(at + 1);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault();
      next();
    }
  };
  return (
    <section data-questions aria-label="Questions" className="overflow-hidden rounded-xl border border-rule bg-panel-2">
      <div className="px-3.5 pb-3 pt-3" aria-live="polite">
        <h3 className="text-[15px] font-medium text-ink">{shown.question}</h3>
        <p className="mt-0.5 text-[13px] text-ink-3">{shown.why}</p>
        {shown.suggestions.length === 0 ? null : (
          <div className="mt-2.5 flex flex-col gap-1">
            {shown.suggestions.map((one) => {
              const on = answer === one;
              return (
                <button
                  key={one}
                  type="button"
                  aria-pressed={on}
                  onClick={() => {
                    answerWith(on ? "" : one);
                  }}
                  className="flex items-center gap-2 rounded-lg px-1.5 py-1 text-left hover:bg-panel"
                >
                  <span className={cn("flex size-4 shrink-0 items-center justify-center rounded-full", on ? "bg-ink" : "shadow-[inset_0_0_0_1.5px_var(--color-rule)]")}>
                    <span className={cn("size-1.5 rounded-full bg-panel-2 transition-transform", on ? "scale-100" : "scale-0")} />
                  </span>
                  <span className={cn("text-[14px]", on ? "text-ink" : "text-ink-2")}>{one}</span>
                </button>
              );
            })}
          </div>
        )}
        <input
          value={answer}
          aria-label="Your answer"
          placeholder="Type an answer"
          onChange={(event) => {
            answerWith(event.target.value);
          }}
          onKeyDown={onKeyDown}
          className="mt-2 w-full rounded-lg border border-rule bg-panel px-2.5 py-1.5 text-[14px] text-ink outline-none placeholder:text-ink-3 focus:border-accent"
        />
        <p data-default className="mt-1 text-[13px] text-ink-3">
          Default: {shown.default}
        </p>
        {problem ? (
          <p role="alert" className="mt-1 text-[13px] text-fail">
            {problem}
          </p>
        ) : null}
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-rule px-3 py-2">
        <div className="flex items-center gap-1 text-ink-3">
          <button
            type="button"
            aria-label="Previous question"
            disabled={at === 0}
            onClick={() => {
              setAt(at - 1);
            }}
            className="rounded p-0.5 enabled:hover:text-ink disabled:opacity-30"
          >
            <ChevronUp aria-hidden className="size-3.5" />
          </button>
          <span className="text-[12px] font-medium tabular-nums">
            {at + 1} / {questions.length}
          </span>
          <button
            type="button"
            aria-label="Next question"
            disabled={last}
            onClick={() => {
              setAt(at + 1);
            }}
            className="rounded p-0.5 enabled:hover:text-ink disabled:opacity-30"
          >
            <ChevronDown aria-hidden className="size-3.5" />
          </button>
        </div>
        <div className="flex items-center gap-1.5">
          <Button variant="ghost" size="sm" disabled={busy} onClick={() => void send()}>
            Skip
          </Button>
          <Button variant="accent" size="sm" disabled={busy} onClick={next}>
            {last ? "Send answers" : "Continue"}
          </Button>
        </div>
      </div>
    </section>
  );
}

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { SignedOutView } from "@/components/Gate";
import { Button } from "@/components/ui/button";
import { ModePicker } from "@/mode/ModePicker";
import { ChatLine } from "./Lines";
import type { Conversation } from "./useConversation";

const SECTION = "font-mono text-[10.5px] uppercase tracking-wider text-ink-2";

function Composer({ chat }: { chat: Conversation }) {
  const { state } = chat;
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const blocked = sending || state.turn === "running";

  const submit = async () => {
    const said = text.trim();
    if (said === "" || blocked) return;
    setSending(true);
    const sent = await chat.send(said);
    setSending(false);
    if (sent) setText("");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    } else if (event.key === "Tab" && event.shiftKey) {
      event.preventDefault();
      void chat.cycle();
    }
  };

  return (
    <form
      className="flex flex-col gap-1.5 border-t border-rule-2 p-2.5"
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      {state.problem !== null ? (
        <p role="alert" className="text-xs text-fail">
          {state.problem}
        </p>
      ) : null}
      <textarea
        aria-label="Message to the agent"
        value={text}
        rows={2}
        placeholder={state.mode === "plan" ? "Describe what you need" : "Ask for a change, such as: make the wall 4 mm"}
        onChange={(event) => {
          setText(event.target.value);
        }}
        onKeyDown={onKeyDown}
        className="w-full resize-none border border-border bg-panel-2 px-2.5 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
      />
      <div className="flex items-center justify-between gap-2">
        <ModePicker mode={state.mode} onPick={(mode) => void chat.pick(mode)} />
        <Button type="submit" variant="accent" size="sm" disabled={blocked || text.trim() === ""}>
          Send
        </Button>
      </div>
    </form>
  );
}

export function ChatPanel({ chat }: { chat: Conversation }) {
  const { state } = chat;
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [state.lines.length, state.turn]);

  return (
    <section aria-label="Chat" className="flex h-full min-h-[320px] flex-col border border-border bg-panel">
      <h3 className="flex items-center justify-between border-b border-rule-2 px-2.5 py-1.5">
        <span className={SECTION}>Chat</span>
        {state.link === "reconnecting" ? <span className="font-mono text-[10px] text-wait">reconnecting</span> : null}
      </h3>
      {state.link === "not_found" ? (
        <p role="status" className="p-3 text-xs text-ink-2">
          This conversation is not in your account.
        </p>
      ) : state.link === "signed_out" ? (
        <SignedOutView />
      ) : (
        <div role="log" aria-live="polite" aria-label="Conversation" className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-2.5 text-[13px]">
          {state.lines.length === 0 ? (
            <p className="text-xs text-ink-2">
              {state.mode === "plan" || state.mode === null
                ? "Start in Plan: say what you need and the agent proposes requirements for you to confirm."
                : "Ask for a change and the agent rebuilds the variant here."}
            </p>
          ) : null}
          {state.lines.map((line) => (
            <ChatLine key={line.seq} line={line} />
          ))}
          {state.turn === "running" ? (
            <p role="status" className="font-mono text-[11.5px] text-ink-3">
              Working…
            </p>
          ) : null}
          <div ref={end} />
        </div>
      )}
      {state.link === "not_found" ? null : <Composer chat={chat} />}
    </section>
  );
}

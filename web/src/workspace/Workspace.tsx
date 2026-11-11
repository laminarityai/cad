import { Files as FilesIcon, Plus } from "lucide-react";
import { useReducer, useState, type Dispatch, type ReactNode } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useServices } from "@/app/context";
import { Gate } from "@/components/Gate";
import { cn } from "@/lib/utils";
import { useResource } from "@/state/resource";
import { Checks } from "./bits";
import { sourcesOf, useCards, type CardKey } from "./cards";
import { CHANGES_PAGE, ChatPane, Composer, useProjectChat } from "./Chat";
import { ConfirmCard } from "./Confirm";
import { loadWorkspace, viewReducer, viewStart, type Brief, type View, type ViewAction, type Workspace as Model } from "./model";
import { BriefList, Files } from "./Nav";
import { SlotTabs, Stage } from "./Stage";
import { useNarrow } from "./useNarrow";

function TopBar(props: { title: string; children?: ReactNode }) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-rule bg-panel px-4">
      <Link to="/new" className="text-[17px] font-semibold tracking-tight" title="Start a new project">
        cad
      </Link>
      <span className="text-ink-3">/</span>
      <span className="truncate text-[16px] font-medium">{props.title}</span>
      <div className="min-w-0 flex-1">{props.children}</div>
    </header>
  );
}

function BriefChips({ briefs, current, dispatch, onNew }: { briefs: Brief[]; current: string; dispatch: Dispatch<ViewAction>; onNew: () => void }) {
  return (
    <nav aria-label="Parts" className="flex items-center gap-1.5 overflow-x-auto">
      {briefs.map((one) => (
        <button
          key={one.id}
          type="button"
          data-brief={one.id}
          aria-current={one.id === current}
          onClick={() => {
            dispatch({ type: "brief", briefId: one.id });
          }}
          className={cn(
            "flex shrink-0 items-center gap-2 rounded-full border px-3 py-1 text-[14px]",
            one.id === current ? "border-accent bg-accent/15" : "border-rule hover:bg-panel-2",
          )}
        >
          {one.title}
          {one.state === "waiting" ? <span className="size-2 rounded-full bg-wait" /> : null}
        </button>
      ))}
      <button type="button" onClick={onNew} className="flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-[14px] text-accent hover:bg-panel-2">
        <Plus className="size-4" /> New part
      </button>
    </nav>
  );
}

const WAITING_TEXT: Record<Brief["state"], string> = {
  drafting: "The agent is writing what it will check.",
  waiting: "Confirm in the chat and the options appear here.",
  building: "Building the options…",
  ready: "",
};

function slotOf(brief: Brief, view: View) {
  const chosen = view.slotOf[brief.id];
  return brief.slots.find((one) => one.slot === chosen) ?? brief.slots[0];
}

function Center({ brief, view, cards, dispatch }: { brief: Brief; view: View; cards: ReturnType<typeof useCards>; dispatch: Dispatch<ViewAction> }) {
  const slot = slotOf(brief, view);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="px-5 pb-2 pt-4">
        <p className="line-clamp-2 text-[17px] leading-snug" title={brief.words} data-brief-words>
          “{brief.words}”
        </p>
      </div>
      {slot ? (
        <>
          <div className="px-4">
            <SlotTabs brief={brief} slot={slot.slot} cards={cards} dispatch={dispatch} />
          </div>
          <div className="mx-4 mb-4 flex min-h-0 flex-1 flex-col overflow-hidden rounded-b-xl rounded-tr-xl border border-t-0 border-rule bg-panel">
            <Stage
              key={`${brief.id}:${String(slot.slot)}`}
              slot={slot}
              revision={view.revisionOf[`${brief.id}:${String(slot.slot)}`] ?? null}
              dispatch={dispatch}
              briefId={brief.id}
              fit={brief.fits[0] ?? null}
            />
          </div>
        </>
      ) : (
        <p className="px-5 py-8 text-[16px] text-ink-2">{WAITING_TEXT[brief.state]}</p>
      )}
    </div>
  );
}

function shown(brief: Brief, view: View): { variantId: string; slot: number } | null {
  const slot = slotOf(brief, view);
  if (!slot) return null;
  const n = view.revisionOf[`${brief.id}:${String(slot.slot)}`] ?? slot.revisions.length;
  const revision = slot.revisions[n - 1];
  return revision ? { variantId: revision.variantId, slot: slot.slot } : null;
}

type Tab = "chat" | "design" | "checks" | "files";

function Page({ model, reload }: { model: Model; reload: () => void }) {
  const { chat: chatApi } = useServices();
  const narrow = useNarrow();
  const [tab, setTab] = useState<Tab>("design");
  const [view, dispatch] = useReducer(viewReducer, viewStart);
  const [answered, setAnswered] = useState<string | null>(null);
  const [placeholder, setPlaceholder] = useState("Ask for a change, a new part, anything");
  const chat = useProjectChat(model.conversationId, (change) => {
    if (change.kind === "turn_ended" || CHANGES_PAGE.has(change.name)) reload();
  });
  const withSets = model.briefs.filter((one) => one.slots.length > 0);
  const brief = model.briefs.find((one) => one.id === view.briefId) ?? withSets[withSets.length - 1] ?? model.briefs[0];
  const keys: CardKey[] = model.briefs.flatMap((one) =>
    one.slots.flatMap((slot) =>
      slot.revisions.map((rev) => ({
        variantId: rev.variantId,
        materialKey: one.materialOf[slot.slot]?.key ?? null,
        briefId: one.id,
      })),
    ),
  );
  const cards = useCards(keys);
  const sources = sourcesOf(cards);
  const waiting = model.confirmation !== null && model.confirmation.snapshot !== answered;
  const onNew = () => {
    setPlaceholder("Describe the new part");
    setTab("chat");
    document.querySelector<HTMLTextAreaElement>("textarea[aria-label=Message]")?.focus();
  };

  if (!brief) return <Navigate to="/new" replace />;
  const onScreen = shown(brief, view);
  const checks = <Checks card={onScreen ? cards[onScreen.variantId] : undefined} material={onScreen ? (brief.materialOf[onScreen.slot] ?? null) : null} />;
  const confirmation = model.confirmation;
  const card =
    waiting && confirmation?.snapshot ? (
      <ConfirmCard
        key={confirmation.snapshot}
        projectId={model.projectId}
        card={{ ...confirmation, snapshot: confirmation.snapshot }}
        onAnswered={(recorded) => {
          if (recorded) setAnswered(confirmation.snapshot);
          reload();
        }}
      />
    ) : null;
  const composer = (
    <Composer
      placeholder={placeholder}
      onSend={async (text) => {
        await chatApi.send(model.conversationId, text);
      }}
    />
  );
  const chatPane = <ChatPane lines={chat.lines} running={chat.turn === "running"} card={card} composer={composer} />;
  const center = <Center brief={brief} view={view} cards={cards} dispatch={dispatch} />;

  if (narrow) {
    const tabs = [
      ["chat", "Chat"],
      ["design", "Design"],
      ["checks", "Checks"],
      ["files", "Files"],
    ] as const;
    return (
      <div className="flex h-dvh flex-col bg-background text-ink">
        <TopBar title={model.title} />
        <div className="border-b border-rule-2 px-3 py-2">
          <BriefChips briefs={model.briefs} current={brief.id} dispatch={dispatch} onNew={onNew} />
        </div>
        <main className="min-h-0 flex-1 overflow-y-auto">
          {tab === "chat" ? chatPane : null}
          {tab === "design" ? <div className="flex h-full flex-col">{center}</div> : null}
          {tab === "checks" ? checks : null}
          {tab === "files" ? (
            <div className="space-y-5 py-4">
              <BriefList briefs={model.briefs} current={brief.id} cards={cards} dispatch={dispatch} onNew={onNew} />
              <Files parts={model.parts} sources={sources} />
            </div>
          ) : null}
        </main>
        <nav aria-label="Panes" className="grid grid-cols-4 border-t border-rule bg-panel">
          {tabs.map(([key, label]) => (
            <button
              key={key}
              type="button"
              aria-current={tab === key}
              onClick={() => {
                setTab(key);
              }}
              className={cn("relative py-3 text-[15px]", tab === key ? "font-semibold text-accent" : "text-ink-2")}
            >
              {label}
              {key === "chat" && waiting ? <span data-waiting className="absolute right-5 top-2.5 size-2 rounded-full bg-wait" /> : null}
            </button>
          ))}
        </nav>
      </div>
    );
  }

  return (
    <div className="flex h-dvh flex-col bg-background text-ink">
      <TopBar title={model.title}>
        <BriefChips briefs={model.briefs} current={brief.id} dispatch={dispatch} onNew={onNew} />
      </TopBar>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(360px,420px)_minmax(0,1fr)_340px]">
        <aside className="min-h-0 border-r border-rule bg-panel">{chatPane}</aside>
        {center}
        <aside className="flex min-h-0 flex-col overflow-y-auto border-l border-rule bg-panel">
          {checks}
          <details className="mt-auto border-t border-rule" open={model.parts.length > 0}>
            <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-[15px] font-semibold">
              <FilesIcon className="size-4" /> Files
            </summary>
            <Files bare parts={model.parts} sources={sources} />
            <div className="h-4" />
          </details>
        </aside>
      </div>
    </div>
  );
}

export function Workspace() {
  const { api } = useServices();
  const { projectId = "" } = useParams();
  const { resource, reload } = useResource(() => loadWorkspace(api, projectId), `workspace:${projectId}`, 3000);
  return <Gate resource={resource}>{(model) => <Page model={model} reload={reload} />}</Gate>;
}

/** A chat with no project yet. The agent's first create_brief makes the project and binds this chat
 * to it, and the page then becomes that project's workspace. */
export function Start() {
  const { chat } = useServices();
  const navigate = useNavigate();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const state = useProjectChat(conversationId, () => {
    if (conversationId === null) return;
    chat.read(conversationId).then(
      (read) => {
        if (read.project_id !== null) void navigate(`/projects/${read.project_id}`, { replace: true });
      },
      () => undefined,
    );
  });
  const send = async (text: string) => {
    const id = conversationId ?? (await chat.create()).conversation_id;
    setConversationId(id);
    await chat.send(id, text);
  };
  if (conversationId !== null) {
    return (
      <div className="flex h-dvh flex-col bg-background text-ink">
        <TopBar title="New project" />
        <main className="mx-auto flex min-h-0 w-full max-w-2xl flex-1 flex-col">
          <ChatPane lines={state.lines} running={state.turn === "running"} card={null} composer={<Composer placeholder="Ask anything" onSend={send} />} />
        </main>
      </div>
    );
  }
  return (
    <div className="flex min-h-dvh flex-col bg-background text-ink">
      <TopBar title="New project" />
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-4 pb-24">
        <h1 className="mb-5 text-center text-[28px] font-semibold tracking-tight">What do you want to make?</h1>
        <Composer big placeholder="A wall hook for a 20 mm rail that holds 5 kg…" onSend={send} />
      </main>
    </div>
  );
}

export function Home() {
  const { api } = useServices();
  const { resource } = useResource(() => api.projects(), "projects");
  return (
    <Gate resource={resource}>
      {({ projects }) => {
        const newest = [...projects].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
        return newest ? <Navigate to={`/projects/${newest.project_id}`} replace /> : <Start />;
      }}
    </Gate>
  );
}

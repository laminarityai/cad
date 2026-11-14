import { useEffect, useReducer, useState, type Dispatch } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { useServices } from "@/app/context";
import { Gate } from "@/components/Gate";
import { summaryOf, toPicked, useSelection, type Selection } from "@/features/viewer/selection";
import type { OnPick } from "@/features/viewer/engine";
import type { Where } from "@/features/viewer/where";
import { Tabs, TabsList, TabsPanel, TabsTab } from "@/components/ui/tabs";
import { Loading } from "@/components/ui/busy";
import { Tooltip } from "@/components/ui/tooltip";
import { sinceOf, stalledOf, workingLabel, workingOf, type Working } from "@/features/chat/working";
import { RunStatus } from "@/features/auto/RunStatus";
import { AUTO_TOOLS } from "@/features/auto/run";
import { useAuto } from "@/features/auto/useAuto";
import { useResource } from "@/state/resource";
import { Checks } from "./bits";
import { linesOf, sourcesOf, useCards, type CardKey } from "./cards";
import { CHANGES_PAGE, ChatPane, Composer, useProjectChat } from "./Chat";
import { ConfirmCard } from "./Confirm";
import { Explorer } from "./Explorer";
import { loadWorkspace, stageKey, viewReducer, viewStart, type Brief, type View, type ViewAction, type Workspace as Model } from "./model";
import { SlotTabs, Stage } from "./Stage";
import { useNarrow } from "./useNarrow";

function TopBar({ title }: { title: string }) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-rule bg-panel px-4">
      <Tooltip label="Start a new project">
        <Link to="/new" className="text-[17px] font-semibold tracking-tight">
          cad
        </Link>
      </Tooltip>
      <span className="text-ink-3">/</span>
      <span className="truncate text-[16px] font-medium">{title}</span>
    </header>
  );
}

function NoOptions({ brief, working }: { brief: Brief; working: Working | null }) {
  if (brief.state === "waiting") return <p className="px-5 py-8 text-[16px] text-ink-2">Your targets wait for your Confirm in the chat.</p>;
  if (working?.briefId === brief.id) return <Loading label={workingLabel(working)} className="px-5 py-8" />;
  return <p className="px-5 py-8 text-[16px] text-ink-2">No options yet. Ask for them in the chat, such as: build three options.</p>;
}

function slotOf(brief: Brief, view: View) {
  const chosen = view.slotOf[brief.id];
  return brief.slots.find((one) => one.slot === chosen) ?? brief.slots[0];
}

function Center(props: {
  brief: Brief;
  view: View;
  cards: ReturnType<typeof useCards>;
  dispatch: Dispatch<ViewAction>;
  where: Where | null;
  selection: Selection | null;
  onPick: OnPick;
  working: Working | null;
}) {
  const { brief, view, cards, dispatch, where, selection, onPick, working } = props;
  const slot = slotOf(brief, view);
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="px-5 pb-2 pt-4">
        <Tooltip label={brief.words}>
          <p className="line-clamp-2 text-[17px] leading-snug" data-brief-words>
            “{brief.words}”
          </p>
        </Tooltip>
      </div>
      {slot ? (
        <Tabs
          value={slot.slot}
          onValueChange={(value: number) => {
            dispatch({ type: "slot", briefId: brief.id, slot: value });
          }}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="px-4">
            <SlotTabs brief={brief} cards={cards} />
          </div>
          <TabsPanel
            value={slot.slot}
            className="mx-4 mb-4 flex min-h-0 flex-1 flex-col overflow-hidden rounded-b-xl rounded-tr-xl border border-t-0 border-rule bg-panel"
          >
            <Stage
              key={stageKey(brief.id, slot.slot)}
              slot={slot}
              revision={view.revisionOf[stageKey(brief.id, slot.slot)] ?? null}
              cut={view.cutOf[stageKey(brief.id, slot.slot)] ?? null}
              dispatch={dispatch}
              briefId={brief.id}
              fit={brief.fits[0] ?? null}
              where={where}
              selection={selection}
              cards={cards}
              onPick={onPick}
            />
          </TabsPanel>
        </Tabs>
      ) : (
        <NoOptions brief={brief} working={working} />
      )}
    </div>
  );
}

function shown(brief: Brief, view: View): { variantId: string; slot: number } | null {
  const slot = slotOf(brief, view);
  if (!slot) return null;
  const n = view.revisionOf[stageKey(brief.id, slot.slot)] ?? slot.revisions.length;
  const revision = slot.revisions[n - 1];
  return revision ? { variantId: revision.variantId, slot: slot.slot } : null;
}

const SELECTED_PLACEHOLDER = "Ask for a change to the selection, such as: make this thicker";

type Pane = "explorer" | "design" | "chat";

const PANES: readonly (readonly [Pane, string])[] = [
  ["explorer", "Explorer"],
  ["design", "Design"],
  ["chat", "Chat"],
];

function Page({ model, reload }: { model: Model; reload: () => void }) {
  const { chat: chatApi } = useServices();
  const narrow = useNarrow();
  const [pane, setPane] = useState<Pane>("design");
  const [view, dispatch] = useReducer(viewReducer, viewStart);
  const [answered, setAnswered] = useState<string | null>(null);
  const [forNewPart, setForNewPart] = useState(false);
  const [sent, setSent] = useState<{ seq: number; at: number } | null>(null);
  const auto = useAuto(model.conversationId);
  const chat = useProjectChat(model.conversationId, (change) => {
    if (change.kind === "turn_ended" || change.kind === "stop_report" || AUTO_TOOLS.has(change.name)) auto.reload();
    if (change.kind === "turn_ended" || (change.kind === "tool" && CHANGES_PAGE.has(change.name))) reload();
  });
  const withSets = model.briefs.filter((one) => one.slots.length > 0);
  const brief = model.briefs.find((one) => one.id === view.briefId) ?? withSets[withSets.length - 1] ?? model.briefs[0];
  const onScreen = brief ? shown(brief, view) : null;
  const { selection, onPick, clear } = useSelection(onScreen?.variantId ?? null);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") clear();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [clear]);
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
  const [asked, setAsked] = useState<{ variantId: string; key: string } | null>(null);
  const shownKey = asked !== null && asked.variantId === onScreen?.variantId ? asked.key : null;
  const snapshot = onScreen ? cards[onScreen.variantId]?.snapshot : null;
  const where = (snapshot && shownKey !== null ? linesOf(snapshot).asked.find((one) => one.key === shownKey)?.where : undefined) ?? null;
  const placeholder = selection ? SELECTED_PLACEHOLDER : forNewPart ? "Describe the new part" : "Ask for a change, such as: make the wall 4 mm";
  const sources = sourcesOf(cards);
  const waiting = model.confirmation !== null && model.confirmation.snapshot !== answered;
  const onNew = () => {
    setForNewPart(true);
    setPane("chat");
    setTimeout(() => {
      document.querySelector<HTMLTextAreaElement>("textarea[aria-label=Message]")?.focus();
    }, 0);
  };

  if (!brief) return <Navigate to="/new" replace />;
  const checks = (
    <Checks
      card={onScreen ? cards[onScreen.variantId] : undefined}
      material={onScreen ? (brief.materialOf[onScreen.slot] ?? null) : null}
      where={{
        shown: where ? shownKey : null,
        hidden: onScreen ? Boolean(view.cutOf[stageKey(brief.id, onScreen.slot)]) : false,
        onToggle: (key) => {
          if (onScreen) setAsked(shownKey === key ? null : { variantId: onScreen.variantId, key });
        },
      }}
    />
  );
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
      selection={selection ? { label: summaryOf(selection), onRemove: clear } : null}
      onSend={async (text) => {
        const at = Date.now();
        const { seq } = await chatApi.send(model.conversationId, text, selection ? toPicked(selection) : undefined);
        setSent({ seq, at });
        clear();
      }}
    />
  );
  const working = workingOf(chat, auto.run);
  const stalled = stalledOf(chat);
  const status = <RunStatus run={auto.run} working={working} stalled={stalled} problem={auto.problem} onStop={() => void auto.stop()} />;
  const chatPane = <ChatPane lines={chat.lines} working={working} stalled={stalled} since={sinceOf(chat, sent)} card={card} composer={composer} status={status} />;
  const center = <Center brief={brief} view={view} cards={cards} dispatch={dispatch} where={where} selection={selection} onPick={onPick} working={working} />;

  const explorer = (
    <Explorer
      projectId={model.projectId}
      briefs={model.briefs}
      current={brief.id}
      slot={slotOf(brief, view)?.slot}
      cards={cards}
      parts={model.parts}
      documents={model.documents}
      sources={sources}
      dispatch={dispatch}
      onNew={onNew}
      working={working}
      onChanged={reload}
    />
  );

  if (narrow) {
    return (
      <Tabs value={pane} onValueChange={setPane} className="flex h-dvh flex-col bg-background text-ink">
        <TopBar title={model.title} />
        <main className="min-h-0 flex-1 overflow-y-auto">
          <TabsPanel value="explorer">
            {explorer}
            <div className="border-t border-rule">{checks}</div>
          </TabsPanel>
          <TabsPanel value="design" className="flex h-full flex-col">
            {center}
          </TabsPanel>
          <TabsPanel value="chat">{chatPane}</TabsPanel>
        </main>
        <TabsList aria-label="Panes" className="grid grid-cols-3 border-t border-rule bg-panel">
          {PANES.map(([key, label]) => (
            <TabsTab key={key} value={key} className="relative py-3 text-[15px] text-ink-2 data-[active]:font-semibold data-[active]:text-accent">
              {label}
              {key === "chat" && waiting ? <span data-waiting className="absolute right-5 top-2.5 size-2 rounded-full bg-wait" /> : null}
            </TabsTab>
          ))}
        </TabsList>
      </Tabs>
    );
  }

  return (
    <div className="flex h-dvh flex-col bg-background text-ink">
      <TopBar title={model.title} />
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(300px,340px)_minmax(0,1fr)_minmax(380px,420px)]">
        <aside className="flex min-h-0 flex-col border-r border-rule bg-panel">
          <div className="max-h-[45%] shrink-0 overflow-y-auto">{explorer}</div>
          <div className="flex min-h-0 flex-1 flex-col border-t border-rule">{checks}</div>
        </aside>
        {center}
        <aside className="min-h-0 border-l border-rule bg-panel">{chatPane}</aside>
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

export function Start() {
  const { chat } = useServices();
  const navigate = useNavigate();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sent, setSent] = useState<{ seq: number; at: number } | null>(null);
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
    const at = Date.now();
    const id = conversationId ?? (await chat.create()).conversation_id;
    setConversationId(id);
    const { seq } = await chat.send(id, text);
    setSent({ seq, at });
  };
  if (conversationId !== null) {
    return (
      <div className="flex h-dvh flex-col bg-background text-ink">
        <TopBar title="New project" />
        <main className="mx-auto flex min-h-0 w-full max-w-2xl flex-1 flex-col">
          <ChatPane lines={state.lines} working={workingOf(state, null)} stalled={stalledOf(state)} since={sinceOf(state, sent)} card={null} composer={<Composer placeholder="Ask anything" onSend={send} />} />
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

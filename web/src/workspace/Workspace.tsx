import { Files as FilesIcon, Plus } from "lucide-react";
import { useReducer, useRef, useState, type Dispatch, type ReactNode } from "react";
import type { Line } from "@/chat/state";
import { Navigate, useParams } from "react-router-dom";
import { useServices } from "@/app/context";
import { Gate } from "@/components/Gate";
import { useNarrow } from "./useNarrow";
import { cn } from "@/lib/utils";
import { useResource } from "@/state/resource";
import { Checks } from "./bits";
import { sourcesOf, useCards, type CardKey, type Line as CheckLine } from "./cards";
import { ChatPane, Composer, ConfirmCard, useProjectChat } from "./Chat";
import { loadWorkspace, viewReducer, viewStart, type Ask, type Brief, type ProjectFile, type View, type ViewAction, type Workspace as Model } from "./model";
import { BriefList, Files, typeOf } from "./Nav";
import { SlotTabs, Stage } from "./Stage";

const RESEARCHED: CheckLine = {
  key: "mock:researched",
  label: "Softens above 60 °C",
  status: "researched",
  value: "60 °C",
  why: "MOCK. The table had no glass transition for this material, so the agent read it from the maker's datasheet. The server fetched the page and checked the quote.",
  formula: "",
  sources: [{ url: "https://prusament.com/materials/pla/", title: "Prusament PLA, technical data (researched)", page: "1", retrieved: "2026-11-10", standard: null, quote: "" }],
};

/** MOCK: what the chat shows when the agent carries on by itself. Nothing is posted; the real build
 * starts the next turn on the server when the answer is recorded (#203). */
function useMockTurns() {
  const [lines, setLines] = useState<Line[]>([]);
  const [pointed, setPointed] = useState<Record<number, string>>({});
  const seq = useRef(1_000_000);
  const next = () => (seq.current += 1);
  const tool = (name: string): Line => ({ seq: next(), kind: "tool", callId: `m${String(seq.current)}`, name, input: {}, result: null });
  const finish = (reply: string) => {
    setTimeout(() => {
      setLines((now) => [
        ...now.map((one) => (one.kind === "tool" ? { ...one, result: { text: "", isError: false } } : one)),
        { seq: next(), kind: "agent", text: reply },
      ]);
    }, 2200);
  };
  const confirmed = (yes: number, no: number) => {
    const said = no === 0 ? `Confirmed ${String(yes)}` : `Confirmed ${String(yes)}, declined ${String(no)}`;
    setLines((now) => [...now, { seq: next(), kind: "driver", text: said }, tool("build_variant"), tool("build_variant"), tool("build_variant"), tool("score_variant")]);
    finish("Built 3 lid options, see the tabs. **Separate lid** passes everything.");
  };
  const pointedChange = (text: string, where: string, option: string) => {
    const at = next();
    setPointed((now) => ({ ...now, [at]: where }));
    setLines((now) => [...now, { seq: at, kind: "user", text }, tool("build_variant"), tool("score_variant")]);
    finish(`Made the plate on **${option}** 3 mm thick. It is the next revision of that option, so you can step back to compare.`);
  };
  return { lines, pointed, confirmed, pointedChange };
}

function useUploads() {
  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [asks, setAsks] = useState<Ask[]>([]);
  const add = (picked: File[]) => {
    for (const file of picked) {
      const type = typeOf(file.name);
      const size = file.size > 1e6 ? `${(file.size / 1e6).toFixed(1)} MB` : `${String(Math.max(1, Math.round(file.size / 1e3)))} KB`;
      if (type === "cad") {
        setFiles((now) => [...now, { kind: "part", name: file.name, facts: "uploaded", state: "waiting", from: "upload" }]);
        setAsks((now) => [...now, { briefId: "upload", briefTitle: "Uploads", rows: [{ id: `up:${file.name}`, kind: "part", text: file.name, quote: "your upload" }] }]);
      } else {
        setFiles((now) => [...now, { kind: "upload", name: file.name, type, size, state: "reading" }]);
        setTimeout(() => {
          setFiles((now) => now.map((one) => (one.kind === "upload" && one.name === file.name ? { ...one, state: "ready" } : one)));
        }, 1200);
      }
    }
  };
  return { files, asks, add };
}

function TopBar(props: { title: string; children?: ReactNode }) {
  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-b border-rule bg-panel px-4">
      <span className="text-[17px] font-semibold tracking-tight">cad</span>
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
          className={cn("flex shrink-0 items-center gap-2 rounded-full border px-3 py-1 text-[14px]", one.id === current ? "border-accent bg-accent/15" : "border-rule hover:bg-panel-2")}
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

function Center({ brief, view, cards, dispatch }: { brief: Brief; view: View; cards: ReturnType<typeof useCards>; dispatch: Dispatch<ViewAction> }) {
  const slotNumber = view.slotOf[brief.id] ?? brief.slots[0]?.slot ?? 1;
  const slot = brief.slots.find((one) => one.slot === slotNumber) ?? brief.slots[0];
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="px-5 pb-2 pt-4">
        <p className="line-clamp-2 text-[17px] leading-snug" data-brief-words>
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
              highlight={view.highlight}
              pointing={view.pointing}
              dispatch={dispatch}
              briefId={brief.id}
              fit={brief.fits[0] ?? null}
            />
          </div>
        </>
      ) : (
        <p className="px-5 py-8 text-[16px] text-ink-2">{brief.state === "waiting" ? "Confirm in the chat and the options appear here." : "Building the options…"}</p>
      )}
    </div>
  );
}

function shownVariant(brief: Brief | undefined, view: View): string | null {
  if (!brief) return null;
  const slotNumber = view.slotOf[brief.id] ?? brief.slots[0]?.slot;
  const slot = brief.slots.find((one) => one.slot === slotNumber);
  if (!slot) return null;
  const n = view.revisionOf[`${brief.id}:${String(slot.slot)}`] ?? slot.revisions.length;
  return slot.revisions[n - 1]?.variantId ?? null;
}

function Page({ model }: { model: Model }) {
  const { chat: chatApi } = useServices();
  const narrow = useNarrow();
  const [tab, setTab] = useState<"chat" | "design" | "checks" | "files">(() => (location.hash.includes("tab=chat") ? "chat" : "design"));
  const [view, dispatch] = useReducer(viewReducer, viewStart);
  const [confirmedAt, setConfirmedAt] = useState(false);
  const mock = useMockTurns();
  const [placeholder, setPlaceholder] = useState("Ask for a change, a new part, anything");
  const uploads = useUploads();
  const chat = useProjectChat(model.conversationId);
  const withSets = model.briefs.filter((one) => one.slots.length > 0);
  const brief = model.briefs.find((one) => one.id === view.briefId) ?? withSets[withSets.length - 1] ?? model.briefs[0];
  const keys: CardKey[] = model.briefs.flatMap((one) =>
    one.slots.flatMap((slot) => slot.revisions.map((rev) => ({ variantId: rev.variantId, materialKey: one.material?.key ?? "", briefId: one.id }))),
  );
  const cards = useCards(keys);
  const shown = shownVariant(brief, view);
  const research = location.hash.includes("research");
  const asks = [...model.asks, ...uploads.asks];
  const files = [...model.files, ...uploads.files];
  const sources = sourcesOf(cards);
  const onNew = () => {
    setPlaceholder("Describe the new part");
    setTab("chat");
    document.querySelector<HTMLTextAreaElement>("textarea[aria-label=Message]")?.focus();
  };

  if (!brief) return <Navigate to="/" />;
  const checks = <Checks card={shown ? cards[shown] : undefined} material={brief.material} extra={research ? [RESEARCHED] : undefined} />;
  const card =
    asks.length > 0 && !confirmedAt ? (
      <ConfirmCard
        asks={asks}
        onDone={(yes, no) => {
          setConfirmedAt(true);
          mock.confirmed(yes, no);
        }}
      />
    ) : null;
  const composer = (
    <Composer
      placeholder={placeholder}
      highlight={view.highlight}
      onClearHighlight={() => {
        dispatch({ type: "highlight", highlight: null });
      }}
      onAttach={uploads.add}
      onSend={async (text) => {
        if (view.highlight) {
          const option = view.highlight.label.split(",")[0] ?? "";
          mock.pointedChange(text, view.highlight.label, option);
          dispatch({ type: "point", on: false });
          return;
        }
        if (model.conversationId) await chatApi.send(model.conversationId, text);
      }}
    />
  );
  const chatPane = (
    <ChatPane
      lines={chat.lines}
      later={mock.lines}
      pointed={mock.pointed}
      running={chat.turn === "running"}
      card={card}
      composer={composer}
      notice={confirmedAt || mock.lines.length > 0 ? "Prototype: nothing was sent to the agent." : null}
    />
  );
  const center = <Center brief={brief} view={view} cards={cards} dispatch={dispatch} />;
  const nav = (
    <div className="space-y-5 py-4">
      <BriefList briefs={model.briefs} current={brief.id} cards={cards} dispatch={dispatch} onNew={onNew} />
      <Files files={files} sources={sources} onFiles={uploads.add} />
    </div>
  );

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
          {tab === "files" ? nav : null}
        </main>
        <nav className="grid grid-cols-4 border-t border-rule bg-panel">
          {tabs.map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => {
                setTab(key);
              }}
              className={cn("relative py-3 text-[15px]", tab === key ? "font-semibold text-accent" : "text-ink-2")}
            >
              {label}
              {key === "chat" && asks.length > 0 ? <span className="absolute right-5 top-2.5 size-2 rounded-full bg-wait" /> : null}
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
          <details className="mt-auto border-t border-rule" open={files.length > 0 || location.hash.includes("files")}>
            <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-[15px] font-semibold">
              <FilesIcon className="size-4" /> Files
            </summary>
            <Files bare files={files} sources={sources} onFiles={uploads.add} />
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
  const { resource } = useResource(() => loadWorkspace(api, projectId), `workspace:${projectId}`, 3000);
  return <Gate resource={resource}>{(model) => <Page model={model} />}</Gate>;
}

export function Start() {
  const { chat } = useServices();
  return (
    <div className="flex min-h-dvh flex-col bg-background text-ink">
      <header className="flex h-14 items-center gap-4 border-b border-rule bg-panel px-4">
        <span className="text-[17px] font-semibold tracking-tight">cad</span>
        <span className="ml-auto grid size-8 place-items-center rounded-full bg-accent/20 text-[14px] font-semibold text-accent">K</span>
      </header>
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center px-4 pb-24">
        <h1 className="mb-5 text-center text-[28px] font-semibold tracking-tight">What do you want to make?</h1>
        <Composer
          big
          placeholder="A wall hook for a 20 mm rail that holds 5 kg…"
          initial={location.hash.includes("typed") ? "A lid for my desk-clip box. It should plug in snugly and print without supports." : ""}
          highlight={null}
          onClearHighlight={() => undefined}
          onAttach={() => undefined}
          onSend={async (text) => {
            const made = await chat.create("", "").catch(() => null);
            if (made) await chat.send(made.conversation_id, text);
          }}
        />
        <p className="mt-3 text-center text-[14px] text-ink-3">Attach a STEP file, a drawing or a datasheet if you have one.</p>
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

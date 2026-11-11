import { vi } from "vitest";
import type { Api } from "@/api/client";
import type { CardHandlers, CardQuery, ScorecardEvents } from "@/api/events";
import type { Scorecard } from "@/api/snapshot";
import type { ChatApi, Follower } from "@/chat/api";
import type { AutoRun, ConversationState, ConversationView, Event, Mode, PersonStop, StopReason, Tessellated, VariantSetView } from "@/api/types";
import type { Mounted, Shapes, ViewerEngine } from "@/features/viewer/engine";
import { brief } from "./fixtures";

export function setOf(variants: string[]): VariantSetView {
  return {
    project_id: "p1",
    brief_id: "b1",
    decision_sha256: "c".repeat(64),
    limit: 5,
    members: variants.map((variant, at) => ({
      slot: at + 1,
      variant_id: variant,
      revision: 1,
      revisions: [{ revision: 1, variant_id: variant, code_sha256: "e".repeat(64), joined_at: "2026-11-10T00:00:00Z" }],
      material: null,
      card_etag: null,
    })),
  };
}

export const meshOf = (name: string): Tessellated => ({
  kind: "tessellated",
  brep_sha256: "b".repeat(64),
  version: "0123456789ab",
  shapes: { name } as unknown as Tessellated["shapes"],
});

export function fakeApi(variants: string[], overrides: Partial<Api> = {}): Api {
  return {
    projects: vi.fn(() => Promise.resolve({ projects: [] })),
    project: vi.fn(() => Promise.resolve({ project_id: "p1", briefs: [] })),
    brief: vi.fn(() => Promise.resolve(brief(true))),
    waiting: vi.fn(() => Promise.resolve({ project_id: "p1", items: [] })),
    variantSet: vi.fn(() => Promise.resolve(setOf(variants))),
    materials: vi.fn(() => Promise.resolve({ materials: [{ key: "prusament-pla", name: "Prusament PLA" }] })),
    view: vi.fn((variantId: string) =>
      Promise.resolve({
        variant_id: variantId,
        brep_sha256: "b".repeat(64),
        mesh: "tessellated" as const,
        mesh_url: `/v1/geometry/0123456789ab/${variantId}.json`,
      }),
    ),
    mesh: vi.fn((url: string) => Promise.resolve(meshOf(url))),
    geometry: vi.fn((variantId: string) => Promise.resolve(meshOf(variantId))),
    ...overrides,
  };
}

export interface Opened {
  query: CardQuery;
  handlers: CardHandlers;
  closed: boolean;
}

export class FakeEvents implements ScorecardEvents {
  readonly opened: Opened[] = [];

  open(query: CardQuery, handlers: CardHandlers): () => void {
    const one: Opened = { query, handlers, closed: false };
    this.opened.push(one);
    handlers.onConnection("live");
    return () => {
      one.closed = true;
    };
  }

  push(snapshot: Scorecard): void {
    const open = this.opened.filter((one) => one.query.variantId === snapshot.variant_id && !one.closed);
    for (const one of open) one.handlers.onSnapshot(snapshot);
  }
}

export class FakeViewer implements ViewerEngine {
  readonly mounted: Shapes[] = [];
  readonly shown: Shapes[] = [];
  stopped = 0;

  mount(_element: HTMLElement, shapes: Shapes): Promise<Mounted> {
    this.mounted.push(shapes);
    return Promise.resolve({
      show: (next: Shapes) => {
        this.shown.push(next);
      },
      stop: () => {
        this.stopped += 1;
      },
    });
  }
}

export class FakeChat implements ChatApi {
  readonly transcript: { seq: number; event: Event }[] = [];
  readonly sent: string[] = [];
  readonly modes: Mode[] = [];
  readonly stops: string[] = [];
  readonly followed: string[] = [];
  mode: Mode = "plan";
  autoRun: AutoRun | null = null;
  onSend: (text: string) => void = () => undefined;
  private readonly open = new Set<Follower>();

  create = vi.fn<ChatApi["create"]>(() => Promise.resolve({ conversation_id: "c_new", mode: this.mode }));

  read = vi.fn(
    (conversationId: string): Promise<ConversationView> =>
      Promise.resolve({
        conversation_id: conversationId,
        mode: this.mode,
        auto_run: this.autoRun?.state.kind === "running" ? this.autoRun.run_id : null,
        project_id: "p1",
        brief_id: "b1",
        run: this.autoRun,
      }),
  );

  send = vi.fn((_conversationId: string, text: string) => {
    this.sent.push(text);
    this.say({ kind: "user", text });
    this.onSend(text);
    return Promise.resolve({ seq: this.transcript.length });
  });

  setMode = vi.fn((conversationId: string, mode: Mode): Promise<ConversationState> => {
    this.modes.push(mode);
    this.mode = mode;
    if (mode !== "auto" && this.autoRun?.state.kind === "running") this.autoRun = stoppedRun(this.autoRun.run_id, "stopped_by_person", "You stopped the run.");
    return Promise.resolve({ conversation_id: conversationId, mode, auto_run: null });
  });

  stop = vi.fn((runId: string): Promise<PersonStop> => {
    this.stops.push(runId);
    this.mode = "design";
    const run = stoppedRun(runId, "stopped_by_person", "You stopped the run.");
    this.autoRun = run;
    return Promise.resolve({ run, conversation: { conversation_id: "c_new", mode: "design", auto_run: null } });
  });

  follow(conversationId: string, after: number, handlers: Follower): () => void {
    this.followed.push(conversationId);
    handlers.onLink("live");
    for (const one of this.transcript) if (one.seq > after) handlers.onEvent(one.seq, one.event);
    this.open.add(handlers);
    return () => {
      this.open.delete(handlers);
    };
  }

  stopsItself(reason: Exclude<StopReason["kind"], "stopped_by_person">, report: string): void {
    const runId = this.autoRun?.run_id ?? "run_1";
    this.autoRun = stoppedRun(runId, reason, report);
    this.mode = "design";
    this.say({ kind: "stop_report", run_id: runId, reason, report });
  }

  say(event: Event): void {
    const seq = this.transcript.length + 1;
    this.transcript.push({ seq, event });
    for (const one of this.open) one.onEvent(seq, event);
  }
}

export function stoppedRun(runId: string, kind: StopReason["kind"], report: string): AutoRun {
  const reasons: { [K in StopReason["kind"]]: Extract<StopReason, { kind: K }> } = {
    all_pass: { kind: "all_pass", researched: [], unverified: [] },
    needs_person: { kind: "needs_person", why: "agent_asked", requirements: [], bounds: [], note: "" },
    account_limit: { kind: "account_limit", refused: null, reason: "" },
    stopped_by_person: { kind: "stopped_by_person" },
  };
  const reason = reasons[kind];
  return { run_id: runId, settling: false, state: { kind: "stopped", start: startOf(), history: [], reason, report } };
}

export function startOf(): Extract<AutoRun["state"], { kind: "running" }>["start"] {
  return {
    kind: "started",
    conversation: "c_new",
    brief_id: "b1",
    project: "p1",
    decision_sha256: "c".repeat(64),
    material_key: "prusament-pla",
    material_reason: null,
    watermark: [],
    conflicts: [],
  };
}

export function runningRun(revisions: number): AutoRun {
  return {
    run_id: "run_1",
    settling: false,
    state: {
      kind: "running",
      start: startOf(),
      history: Array.from({ length: revisions }, (_, at) => ({
        revision: at + 1,
        variant_id: `v${String(at + 1)}`,
        code_sha256: "e".repeat(64),
        built: true,
        marks: [],
      })),
    },
  };
}

import { act } from "@testing-library/react";
import { vi } from "vitest";
import type { Api } from "@/api/client";
import type { ChatApi, Follower } from "@/api/chat";
import type { AutoRun, ConversationView, Event, ExportFormat, Picked, PersonStop, StopReason, Tessellated, VariantSetView } from "@/api/types";
import type { ScreenPoint } from "@/features/viewer/dimensions";
import type { Mounted, OnPick, Shapes, ViewerEngine } from "@/features/viewer/engine";
import type { MeshReading } from "@/features/viewer/readout";
import type { Section } from "@/features/viewer/section";
import type { Pick } from "@/features/viewer/selection";
import { brief } from "./fixtures";

export function setOf(variants: string[]): VariantSetView {
  return {
    project_id: "p1",
    brief_id: "b1",
    limit: 5,
    members: variants.map((variant, at) => ({
      slot: at + 1,
      variant_id: variant,
      revision: 1,
      revisions: [
        {
          revision: 1,
          variant_id: variant,
          code_sha256: "e".repeat(64),
          joined_at: "2026-11-10T00:00:00Z",
        },
      ],
      material: null,
      option: null,
      material_name: null,
      card_etag: null,
    })),
  };
}

export const meshOf = (name: string): Tessellated => ({
  kind: "tessellated",
  brep_sha256: "b".repeat(64),
  version: "0123456789ab",
  shapes: { name } as unknown as Tessellated["shapes"],
  topology: { faces: [], edges: [] },
});

export function fakeApi(variants: string[], overrides: Partial<Api> = {}): Api {
  return {
    projects: vi.fn(() => Promise.resolve({ projects: [] })),
    project: vi.fn(() => Promise.resolve({ project_id: "p1", briefs: [], context_parts: [], documents: [] })),
    brief: vi.fn(() => Promise.resolve(brief(true))),
    conversation: vi.fn(() => Promise.resolve({ conversation_id: "c1" })),
    confirmation: vi.fn(() => Promise.resolve({ snapshot: null, items: [] })),
    answer: vi.fn(() => Promise.resolve({ status: 200, text: "" })),
    scorecard: vi.fn(() => Promise.reject(new Error("no scorecard in this test"))),
    variantSet: vi.fn(() => Promise.resolve(setOf(variants))),
    materials: vi.fn(() =>
      Promise.resolve({
        materials: [{ key: "prusament-pla", name: "Prusament PLA" }],
      }),
    ),
    view: vi.fn((variantId: string) =>
      Promise.resolve({
        variant_id: variantId,
        brep_sha256: "b".repeat(64),
        mesh: "tessellated" as const,
        mesh_url: `/v1/geometry/0123456789ab/${variantId}.json`,
        areas: [],
      }),
    ),
    mesh: vi.fn((url: string) => Promise.resolve(meshOf(url))),
    geometry: vi.fn((variantId: string) => Promise.resolve(meshOf(variantId))),
    exportOf: vi.fn((variantId: string, _briefId: string, format: ExportFormat) =>
      Promise.resolve({ kind: "ready" as const, url: `/v1/exports/0123456789ab/${"b".repeat(64)}.${format}?name=${variantId}`, filename: `${variantId}.${format}` }),
    ),
    addFile: vi.fn((_projectId: string, file: File) =>
      Promise.resolve({ kind: "document" as const, part: null, document: { file_id: "file-0123456789abcdef", name: file.name, media_type: "application/pdf" as const, size: file.size, withheld: false } }),
    ),
    declinePart: vi.fn((_projectId: string, partId: string) => Promise.resolve({ part_id: partId, declined: true })),
    ...overrides,
  };
}

export class FakeViewer implements ViewerEngine {
  readonly mounted: Shapes[] = [];
  readonly shown: Shapes[] = [];
  /** Every call to `select`, newest last. */
  readonly selected: (readonly Pick[])[] = [];
  private readonly listeners: OnPick[] = [];
  /** Every plane the viewer was told to cut with, newest last. Null is the whole part. */
  readonly sections: (Section | null)[] = [];
  stopped = 0;
  /** What `measure` answers: the mesh's closest-point distance and angle for any two picks. */
  reading: MeshReading | null = null;
  /** Where `track` says a world point lands: the point's x and y, so a test can tell where a line went. */
  project = (point: readonly [number, number, number]): ScreenPoint | null => ({ x: point[0], y: point[1] });

  mount(_element: HTMLElement, shapes: Shapes, _theme: unknown, onPick: OnPick): Promise<Mounted> {
    this.mounted.push(shapes);
    this.listeners.push(onPick);
    return Promise.resolve({
      show: (next: Shapes) => {
        this.shown.push(next);
      },
      select: (picks) => {
        this.selected.push(picks);
      },
      measure: () => this.reading,
      section: (plane) => {
        this.sections.push(plane);
      },
      track: (points, listener) => {
        listener(points.map(this.project));
        return () => undefined;
      },
      stop: () => {
        this.stopped += 1;
      },
    });
  }

  /** What the person sees highlighted now. */
  get highlighted(): readonly Pick[] {
    return this.selected[this.selected.length - 1] ?? [];
  }

  /** The plane the part is cut with now. */
  get cut(): Section | null {
    return this.sections[this.sections.length - 1] ?? null;
  }

  /** The person clicks what is under the cursor on the newest canvas. */
  pick(pick: Pick | null, shift = false): void {
    act(() => {
      this.listeners[this.listeners.length - 1]?.(pick, shift);
    });
  }
}

const plural = (n: number, word: string) => `${String(n)} ${word}${n === 1 ? "" : "s"}`;

function noteOf(picked: Picked) {
  const parts = [(picked.faces ?? []).length > 0 ? plural((picked.faces ?? []).length, "face") : "", (picked.edges ?? []).length > 0 ? plural((picked.edges ?? []).length, "edge") : ""];
  return {
    selection_id: "sel-1",
    summary: picked.part === true ? "Whole part" : parts.filter((one) => one !== "").join(", "),
    brief_id: "b1",
    slot: 1,
    revision: 1,
  };
}

export class FakeChat implements ChatApi {
  readonly transcript: { seq: number; event: Event }[] = [];
  readonly sent: string[] = [];
  readonly picked: (Picked | undefined)[] = [];
  readonly stops: string[] = [];
  readonly followed: string[] = [];
  autoRun: AutoRun | null = null;
  stoppedRun: string | null = null;
  briefId: string | null = "b1";
  onSend: (text: string) => void = () => undefined;
  private readonly open = new Set<Follower>();

  create = vi.fn<ChatApi["create"]>(() => Promise.resolve({ conversation_id: "c_new" }));

  read = vi.fn((conversationId: string): Promise<ConversationView> =>
    Promise.resolve({
      conversation_id: conversationId,
      auto_run: this.autoRun?.state.kind === "running" ? this.autoRun.run_id : null,
      stopped_run: this.stoppedRun,
      project_id: "p1",
      brief_id: this.briefId,
      run: this.autoRun,
    }),
  );

  send = vi.fn((_conversationId: string, text: string, selection?: Picked) => {
    this.sent.push(text);
    this.picked.push(selection);
    this.stoppedRun = null;
    this.say({ kind: "user", text, selection: selection ? noteOf(selection) : null });
    this.onSend(text);
    return Promise.resolve({ seq: this.transcript.length });
  });

  stop = vi.fn((runId: string): Promise<PersonStop> => {
    this.stops.push(runId);
    this.stoppedRun = runId;
    const run = stoppedRun(runId, "stopped_by_person", "You stopped the run.");
    this.autoRun = run;
    return Promise.resolve({
      run,
      conversation: {
        conversation_id: "c_new",
        auto_run: null,
        stopped_run: runId,
      },
    });
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
    this.stoppedRun = runId;
    this.say({ kind: "stop_report", run_id: runId, reason, report });
  }

  drop(): void {
    for (const one of this.open) one.onLink("reconnecting");
  }

  say(event: Event): void {
    const seq = this.transcript.length + 1;
    this.transcript.push({ seq, event });
    for (const one of this.open) one.onEvent(seq, event);
  }
}

export function stoppedRun(runId: string, kind: StopReason["kind"], report: string): AutoRun {
  const reasons: {
    [K in StopReason["kind"]]: Extract<StopReason, { kind: K }>;
  } = {
    all_pass: { kind: "all_pass", researched: [], unverified: [], agent_checked: [] },
    needs_person: {
      kind: "needs_person",
      why: "agent_asked",
      requirements: [],
      bounds: [],
      note: "",
    },
    account_limit: { kind: "account_limit", refused: null, reason: "" },
    stopped_by_person: { kind: "stopped_by_person" },
  };
  const reason = reasons[kind];
  return {
    run_id: runId,
    settling: false,
    state: { kind: "stopped", start: startOf(), history: [], builds: [], reason, report },
  };
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
      builds: Array.from({ length: revisions }, (_, at) => String(at + 1).repeat(64)),
    },
  };
}

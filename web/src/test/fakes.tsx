import { vi } from "vitest";
import type { Api } from "@/api/client";
import type { CardHandlers, CardQuery, ScorecardEvents } from "@/api/events";
import type { ScorecardSnapshot, Tessellated, VariantSetView } from "@/api/types";
import type { Shapes, ViewerEngine } from "@/features/viewer/engine";
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

  push(snapshot: ScorecardSnapshot): void {
    const open = this.opened.filter((one) => one.query.variantId === snapshot.variant_id && !one.closed);
    for (const one of open) one.handlers.onSnapshot(snapshot);
  }
}

export class FakeViewer implements ViewerEngine {
  readonly mounted: Shapes[] = [];
  stopped = 0;

  mount(_element: HTMLElement, shapes: Shapes): Promise<() => void> {
    this.mounted.push(shapes);
    return Promise.resolve(() => {
      this.stopped += 1;
    });
  }
}

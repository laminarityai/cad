import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import type { Component, Tessellated } from "@/api/types";
import type { Shapes } from "@/features/viewer/engine";
import { SUPPLIED_COLOUR } from "@/features/viewer/supplied";
import { FakeChat, FakeViewer, fakeApi } from "@/test/fakes";
import { snapshot } from "@/test/fixtures";
import { Workspace } from "./Workspace";

const WHEEL = "part-0123456789abcdef";
const WHEEL_SHA = "a1b2c3d4e5f6".padEnd(64, "0");
const CORNERS = [-40, 40].flatMap((x) => [-25, 25].map((y) => ({ at: [x, y, 0] as [number, number, number], rotate: [90, 0, 0] as [number, number, number] })));
const WHEEL_URL = `/v1/geometry/0123456789ab/${WHEEL_SHA}.json`;

const shapesOf = (bb: Shapes["bb"]) =>
  ({
    version: 3,
    id: "/variant",
    name: "variant",
    loc: [[0, 0, 0], [0, 0, 0, 1]],
    normal_len: 0,
    parts: [{ id: "/variant/part", name: "part", color: "#a6abb0", alpha: 1, loc: [[0, 0, 0], [0, 0, 0, 1]], shape: { triangles: [0, 1, 2] } }],
    bb,
  }) as unknown as Shapes;

// The view is read again every 500 ms while a supplied part's mesh is pending: a hundredth of that here.
vi.mock("@/lib/sleep", () => ({ sleep: (ms: number) => new Promise<void>((done) => setTimeout(done, ms / 100)) }));

type Meshing = (reads: number) => Component["mesh"];

const meshOf = (shapes: Shapes): Tessellated => ({ kind: "tessellated", brep_sha256: "b".repeat(64), version: "0123456789ab", shapes, topology: { faces: [], edges: [] }, solid_faces: [] });

function open(meshing: Meshing = (reads) => (reads === 1 ? "pending" : "tessellated")) {
  const viewer = new FakeViewer();
  const wheel = (mesh: Component["mesh"]): Component => ({ part_id: WHEEL, brep_sha256: WHEEL_SHA, mesh, mesh_url: mesh === "tessellated" ? WHEEL_URL : null, placements: CORNERS });
  let reads = 0;
  const api = fakeApi(["v1"], {
    project: vi.fn(() =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] }),
    ),
    scorecard: vi.fn(() =>
      Promise.resolve({
        ...snapshot("v1", [], []),
        brep_sha256: "9f8e7d6c5b4a".padEnd(64, "0"),
        supplied: [{ part_id: WHEEL, name: "wheel", origin: { kind: "upload" as const, file_name: "wheel.step" }, brep_sha256: WHEEL_SHA, placements: CORNERS }],
      }),
    ),
    view: vi.fn((variantId: string) => {
      reads += 1;
      return Promise.resolve({
        variant_id: variantId,
        brep_sha256: "b".repeat(64),
        mesh: "tessellated" as const,
        mesh_url: `/v1/geometry/0123456789ab/${variantId}.json`,
        areas: [],
        bodies: [],
        components: [wheel(meshing(reads))],
      });
    }),
    mesh: vi.fn((url: string) =>
      Promise.resolve(
        meshOf(url === WHEEL_URL ? shapesOf({ xmin: -10, xmax: 10, ymin: -10, ymax: 10, zmin: 0, zmax: 8 }) : shapesOf({ xmin: -50, xmax: 50, ymin: -30, ymax: 30, zmin: 0, zmax: 5 })),
      ),
    ),
  });
  render(
    <ServicesProvider services={{ api, viewer, chat: new FakeChat() }}>
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <Routes>
          <Route path="projects/:projectId" element={<Workspace />} />
        </Routes>
      </MemoryRouter>
    </ServicesProvider>,
  );
  return { viewer, reads: () => reads };
}

const drawnParts = (viewer: FakeViewer) => [...viewer.mounted, ...viewer.shown].at(-1)?.parts ?? [];

describe("the parts a person supplied", () => {
  it("are listed on the card apart from the body the agent made, which alone is checked", async () => {
    open();
    const list = await screen.findByRole("list", { name: "Parts" });
    const made = list.querySelector('[data-part="made"]');
    if (!(made instanceof HTMLElement)) throw new Error("the made row is missing");
    expect(within(made).getByText("made by the agent")).toBeInTheDocument();
    expect(within(made).getByText("BREP 9f8e7d6c5b4a")).toBeInTheDocument();
    const wheel = list.querySelector(`[data-part="${WHEEL}"]`);
    if (!(wheel instanceof HTMLElement)) throw new Error("the wheel row is missing");
    expect(within(wheel).getByText("supplied by you, placed by the agent · not checked")).toBeInTheDocument();
    expect(within(wheel).getByText("4 copies")).toBeInTheDocument();
    expect(within(wheel).getByText("wheel.step · BREP a1b2c3d4e5f6")).toBeInTheDocument();
  });

  it("are drawn on the stage at each placement in their own colour once their mesh is made", async () => {
    const { viewer } = open();
    await waitFor(
      () => {
        const drawn = [...viewer.mounted, ...viewer.shown].at(-1);
        expect(drawn?.parts.filter((one) => one.id.startsWith("/supplied/"))).toHaveLength(4);
      },
      { timeout: 3000 },
    );
    const drawn = [...viewer.mounted, ...viewer.shown].at(-1);
    const copies = drawn?.parts.filter((one) => one.id.startsWith("/supplied/")) ?? [];
    expect(copies.map((one) => one.loc[0])).toEqual(CORNERS.map((one) => one.at));
    expect(new Set(copies.map((one) => one.color))).toEqual(new Set([SUPPLIED_COLOUR]));
    // Turned 90 degrees about X, each wheel's 8 mm height lies along -Y from where it sits.
    expect(drawn?.bb.ymin).toBe(-33);
    expect(await screen.findByText("Supplied by you, placed by the agent")).toBeInTheDocument();
  });

  it.each<[string, Meshing]>([
    ["failed", (reads) => (reads < 3 ? "pending" : "failed")],
    ["never made", () => "pending"],
  ])("are left out with a note when their mesh is %s, and the view stops being read", async (_, meshing) => {
    const { viewer, reads } = open(meshing);
    expect(await screen.findByText("A part you supplied could not be drawn", undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(drawnParts(viewer).map((one) => one.id)).toEqual(["/variant/part"]);
    const settled = reads();
    await new Promise((done) => setTimeout(done, 100));
    expect(reads()).toBe(settled);
    expect(settled).toBeLessThanOrEqual(152);
  });
});

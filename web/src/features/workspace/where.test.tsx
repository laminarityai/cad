import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { restore } from "@/api/snapshot";
import type { Checked, Tessellated } from "@/api/types";
import type { Shapes } from "@/features/viewer/engine";
import { FakeChat, FakeViewer, fakeApi, meshOf } from "@/test/fakes";
import { deflectionDone, massResult, snapshot } from "@/test/fixtures";
import type { DoneCheck } from "@/api/snapshot";
import { linesOf } from "./cards";
import { Workspace } from "./Workspace";

const SHAPES = {
  version: 3,
  id: "/variant",
  name: "variant",
  parts: [
    {
      version: 3,
      id: "/variant/part",
      name: "part",
      type: "shapes",
      subtype: "solid",
      shape: {
        vertices: [0, 0, 0, 1, 0, 0, 0, 1, 0],
        normals: [0, 0, 1, 0, 0, 1, 0, 0, 1],
        triangles: [0, 1, 2, 0, 1, 2],
        triangles_per_face: [1, 1],
        face_types: [0, 0],
        edges: [],
        segments_per_edge: [],
        edge_types: [],
        obj_vertices: [],
      },
      state: [1, 1],
      color: "#e8b024",
      alpha: 1,
      texture: null,
      loc: [[0, 0, 0], [0, 0, 0, 1]],
      renderback: false,
      accuracy: 0.01,
      bb: null,
    },
  ],
  loc: [[0, 0, 0], [0, 0, 0, 1]],
  normal_len: 0,
  bb: { xmin: 0, xmax: 1, ymin: 0, ymax: 1, zmin: 0, zmax: 0 },
} as unknown as Shapes;

const feaResult = (instance: string, where?: { support: number[]; load: number[] }): DoneCheck => ({
  ...massResult(),
  check_id: "fea",
  measured: [],
  instance,
  ...(where ? { where } : {}),
});

const stress = (instance: string, extra: Partial<Checked> = {}): Checked => ({ ...deflectionDone(), instance, ...extra });

describe("the faces on a stress requirement's row", () => {
  it("come from the result of that requirement's own load case", () => {
    const wire = snapshot(
      "v1",
      [stress("case-a", { requirement_id: "r2" }), stress("case-b", { requirement_id: "r3" }), stress("case-c", { requirement_id: "r4" })],
      [feaResult("case-a", { support: [0], load: [1] }), feaResult("case-b", { support: [], load: [] }), feaResult("case-c")],
    );
    const { asked } = linesOf(restore(wire));
    expect(asked.map((one) => one.where)).toEqual([{ support: [0], load: [1] }, undefined, undefined]);
  });

  it("are not on a row of another check", () => {
    const wire = snapshot("v1", [{ ...deflectionDone(), check_id: "mass", instance: "" }], [{ ...massResult(), where: { support: [0], load: [1] } }]);
    expect(linesOf(restore(wire)).asked[0]?.where).toBeUndefined();
  });
});

async function open(withWhere: boolean) {
  const viewer = new FakeViewer();
  const wire = snapshot("v1", [stress("case-a")], [feaResult("case-a", withWhere ? { support: [0], load: [1] } : undefined)]);
  const scorecard = vi.fn(() => Promise.resolve(wire));
  const api = fakeApi(["v1"], {
    project: vi.fn(() =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] }),
    ),
    scorecard,
    mesh: vi.fn(() => Promise.resolve({ ...meshOf("v1"), shapes: SHAPES } as Tessellated)),
  });
  const { container } = render(
    <ServicesProvider services={{ api, viewer, chat: new FakeChat() }}>
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <Routes>
          <Route path="projects/:projectId" element={<Workspace />} />
        </Routes>
      </MemoryRouter>
    </ServicesProvider>,
  );
  await waitFor(() => {
    expect(viewer.mounted).toHaveLength(1);
  });
  return { viewer, container, scorecard };
}

const ids = (shapes: Shapes | undefined) => shapes?.parts.map((one) => one.id);

describe("showing where the check held and pushed", () => {
  it("draws the two faces in their own colours with a legend, and puts the part back when it is toggled off", async () => {
    const { viewer, container } = await open(true);
    expect(ids(viewer.mounted[0])).toEqual(["/variant/part"]);
    expect(container.querySelector("[data-where-legend]")).toBeNull();
    const button = await screen.findByRole("button", { name: "Show where it held and pushed" });
    expect(button).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(button);
    await waitFor(() => {
      expect(ids(viewer.shown[viewer.shown.length - 1])).toEqual(["/variant/part", "/variant/support", "/variant/load"]);
    });
    expect(screen.getByRole("button", { name: "Showing where it held and pushed" })).toHaveAttribute("aria-pressed", "true");
    const legend = container.querySelector("[data-where-legend]");
    expect(legend).toHaveTextContent("Held in place");
    expect(legend).toHaveTextContent("Pushed on");
    await userEvent.click(screen.getByRole("button", { name: "Showing where it held and pushed" }));
    await waitFor(() => {
      expect(ids(viewer.shown[viewer.shown.length - 1])).toEqual(["/variant/part"]);
    });
    expect(container.querySelector("[data-where-legend]")).toBeNull();
  });

  it("is not drawn again when the scorecard is read again with the same faces", async () => {
    const { viewer, scorecard } = await open(true);
    await userEvent.click(await screen.findByRole("button", { name: "Show where it held and pushed" }));
    await waitFor(() => {
      expect(viewer.shown).toHaveLength(1);
    });
    const reads = scorecard.mock.calls.length;
    await waitFor(
      () => {
        expect(scorecard.mock.calls.length).toBeGreaterThanOrEqual(reads + 2);
      },
      { timeout: 5000 },
    );
    expect(viewer.shown).toHaveLength(1);
  }, 10000);

  it("is not offered when the result carries no faces", async () => {
    const { container } = await open(false);
    await waitFor(() => {
      expect(container.querySelector("[data-line]")).not.toBeNull();
    });
    expect(screen.queryByRole("button", { name: /where it held/ })).toBeNull();
  });
});

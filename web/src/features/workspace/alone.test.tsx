import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import type { Tessellated } from "@/api/types";
import type { Shapes } from "@/features/viewer/engine";
import { FakeChat, FakeViewer, fakeApi, meshOf, setOf } from "@/test/fakes";
import { Workspace } from "./Workspace";

/** Two faces of one triangle each: face 0 is the plate and face 1 is the gear. */
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
      color: "#a6abb0",
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

const AGENT = { kind: "agent_argument" as const, statement: "The agent chose this material." };

async function open() {
  const viewer = new FakeViewer();
  const members = setOf(["v1"]).members.map((member) => ({
    ...member,
    body_materials: [
      { body: "plate", key: "polymaker-fiberon-pa6-cf20", name: "Polymaker Fiberon PA6-CF20", set_by: AGENT },
      { body: "gear", key: "cliffs-hot-rolled-cs-type-b", name: "Cleveland-Cliffs hot-rolled steel", set_by: AGENT },
    ],
  }));
  const api = fakeApi(["v1"], {
    project: vi.fn(() =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] }),
    ),
    variantSet: vi.fn(() => Promise.resolve({ ...setOf(["v1"]), members })),
    view: vi.fn((variantId: string) =>
      Promise.resolve({
        variant_id: variantId,
        brep_sha256: "b".repeat(64),
        mesh: "tessellated" as const,
        mesh_url: `/v1/geometry/0123456789ab/${variantId}.json`,
        areas: [],
        bodies: [
          { name: "plate", faces: [0] },
          { name: "gear", faces: [1] },
        ],
      }),
    ),
    mesh: vi.fn(() => Promise.resolve({ ...meshOf("v1"), shapes: SHAPES } as Tessellated)),
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
  await waitFor(() => {
    expect(viewer.mounted).toHaveLength(1);
  });
  return viewer;
}

const perFace = (shapes: Shapes | undefined) => shapes?.parts[0]?.shape.triangles_per_face;

describe("a body shown alone", () => {
  it("draws only that body's faces on a click on it in the explorer, and the whole model again on a second click", async () => {
    const viewer = await open();
    expect(perFace(viewer.mounted[0])).toEqual([1, 1]);
    await userEvent.click(await screen.findByRole("button", { name: /^gear/ }));
    await waitFor(() => {
      expect(perFace(viewer.shown[viewer.shown.length - 1])).toEqual([0, 1]);
    });
    await userEvent.click(screen.getByRole("button", { name: /^gear/ }));
    await waitFor(() => {
      expect(perFace(viewer.shown[viewer.shown.length - 1])).toEqual([1, 1]);
    });
  });

  it("moves to the other body on a click on it", async () => {
    const viewer = await open();
    await userEvent.click(await screen.findByRole("button", { name: /^gear/ }));
    await userEvent.click(screen.getByRole("button", { name: /^plate/ }));
    await waitFor(() => {
      expect(perFace(viewer.shown[viewer.shown.length - 1])).toEqual([1, 0]);
    });
  });
});

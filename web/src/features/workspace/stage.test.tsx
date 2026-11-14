import { render, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { FakeChat, FakeViewer, fakeApi, meshOf } from "@/test/fakes";
import { Workspace } from "./Workspace";

describe("the stage", () => {
  it("asks for the part's mesh once when there is no part to fit", async () => {
    const viewer = new FakeViewer();
    const view = vi.fn((variantId: string) => Promise.resolve({ variant_id: variantId, brep_sha256: "b".repeat(64), mesh: "tessellated" as const, mesh_url: `/v1/geometry/0123456789ab/${variantId}.json`, areas: [] }));
    const mesh = vi.fn((url: string) => Promise.resolve(meshOf(url)));
    const project = () =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] });
    render(
      <ServicesProvider services={{ api: fakeApi(["v1"], { project, view, mesh }), viewer, chat: new FakeChat() }}>
        <MemoryRouter initialEntries={["/projects/p1"]}>
          <Routes>
            <Route path="projects/:projectId" element={<Workspace />} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>,
    );
    await waitFor(() => {
      expect(viewer.selected.length).toBeGreaterThan(0);
    });
    expect(view).toHaveBeenCalledTimes(1);
    expect(mesh).toHaveBeenCalledTimes(1);
  });
});

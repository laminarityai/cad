import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { Refused } from "@/api/client";
import { FakeChat, FakeViewer, fakeApi, meshOf } from "@/test/fakes";
import { Workspace } from "./Workspace";

describe("the stage", () => {
  it("asks for the part's mesh once when there is no part to fit", async () => {
    const viewer = new FakeViewer();
    const view = vi.fn((variantId: string) => Promise.resolve({ variant_id: variantId, brep_sha256: "b".repeat(64), mesh: "tessellated" as const, mesh_url: `/v1/geometry/0123456789ab/${variantId}.json`, areas: [], bodies: [], components: [] }));
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

  it("offers one Rebuild button for an option an earlier version built, and asks the server to rebuild it", async () => {
    const outdated = () => Promise.reject(new Refused(409, "variant v1 was stored by an earlier version of the sandbox", "OutdatedVariant"));
    const rebuild = vi.fn(() => Promise.resolve({ variant_id: "v2", rebuilt_from: "v1" }));
    const project = () =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] });
    render(
      <ServicesProvider services={{ api: fakeApi(["v1"], { project, view: outdated, scorecard: outdated, rebuild }), viewer: new FakeViewer(), chat: new FakeChat() }}>
        <MemoryRouter initialEntries={["/projects/p1"]}>
          <Routes>
            <Route path="projects/:projectId" element={<Workspace />} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>,
    );
    const button = await screen.findByRole("button", { name: "Rebuild" });
    expect(screen.getAllByText(/built before an app update/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /download/i })).toBeNull();
    await userEvent.click(button);
    expect(rebuild).toHaveBeenCalledWith("v1", "b1");
  });
  it("offers Rebuild for an option whose stored files do not match its build, so the server can heal it", async () => {
    const damaged = () => Promise.reject(new Refused(409, "variant v1 has a result.brep that its build did not store", "DamagedShape"));
    const rebuild = vi.fn(() => Promise.resolve({ variant_id: "v1", rebuilt_from: null }));
    const project = () =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] });
    render(
      <ServicesProvider services={{ api: fakeApi(["v1"], { project, view: damaged, rebuild }), viewer: new FakeViewer(), chat: new FakeChat() }}>
        <MemoryRouter initialEntries={["/projects/p1"]}>
          <Routes>
            <Route path="projects/:projectId" element={<Workspace />} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>,
    );
    const button = await screen.findByRole("button", { name: "Rebuild" });
    expect(screen.getByText(/stored files do not match its build/i)).toBeTruthy();
    await userEvent.click(button);
    expect(rebuild).toHaveBeenCalledWith("v1", "b1");
  });
  it("offers no Rebuild for a damaged option the server cannot heal, and points to the chat", async () => {
    const damaged = () => Promise.reject(new Refused(409, "variant v1's build record failed the server's integrity check", "StaleVariant"));
    const project = () =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] });
    render(
      <ServicesProvider services={{ api: fakeApi(["v1"], { project, view: damaged }), viewer: new FakeViewer(), chat: new FakeChat() }}>
        <MemoryRouter initialEntries={["/projects/p1"]}>
          <Routes>
            <Route path="projects/:projectId" element={<Workspace />} />
          </Routes>
        </MemoryRouter>
      </ServicesProvider>,
    );
    expect((await screen.findAllByText(/ask in the chat/i)).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Rebuild" })).toBeNull();
  });
});

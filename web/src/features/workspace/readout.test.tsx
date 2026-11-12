import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import type { Tessellated } from "@/api/types";
import { FakeChat, FakeViewer, fakeApi, meshOf } from "@/test/fakes";
import { Workspace } from "./Workspace";

const plane = (area: number, center: [number, number, number], normal: [number, number, number]) => ({ type: "PLANE", area, center, normal, radius: null, axis: null, edges: [] });
const topology: Tessellated["topology"] = {
  faces: [
    plane(3540, [0, 20, 5], [0, 0, 1]),
    plane(300, [0, 2.5, 70], [0, 0, 1]),
    { type: "CYLINDER", area: 95.03, center: [18, 10, 2.5], normal: [1, 0, 0], radius: 2.75, axis: [0, 0, 1], edges: [] },
  ],
  edges: [],
};

async function open(viewer: FakeViewer, chat = new FakeChat()) {
  const api = fakeApi(["v1"], {
    project: vi.fn(() =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] }),
    ),
    mesh: vi.fn((url: string) => Promise.resolve({ ...meshOf(url), topology })),
  });
  render(
    <ServicesProvider services={{ api, viewer, chat }}>
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
  return { chat, region: screen.getByRole("status", { name: "Measurements of the selection" }) };
}

describe("the readout for the selection", () => {
  it("is empty until something is picked, then shows the face's facts and says it is not a check", async () => {
    const viewer = new FakeViewer();
    const { region } = await open(viewer);
    expect(region).toBeEmptyDOMElement();
    viewer.pick({ kind: "face", index: 0 });
    expect(within(region).getAllByRole("listitem").map((one) => one.textContent)).toEqual(["Planar face", "Area 3540.00 mm²", "Measured on screen. Not a check."]);
  });

  it("names the gap between two parallel planes and asks the viewer for the closest points", async () => {
    const viewer = new FakeViewer();
    viewer.reading = { distance: 65.28, angle: 0 };
    const { region } = await open(viewer);
    viewer.pick({ kind: "face", index: 0 });
    viewer.pick({ kind: "face", index: 1 }, true);
    await waitFor(() => {
      expect(region).toHaveTextContent("Gap between the planes 65.00 mm");
    });
    expect(region).toHaveTextContent("Closest points 65.28 mm");
    expect(region).not.toHaveTextContent("≈");
  });

  it("starts the mesh's numbers with ≈ when a pick is curved, and goes away for three picks", async () => {
    const viewer = new FakeViewer();
    viewer.reading = { distance: 2.5, angle: 90 };
    const { region } = await open(viewer);
    viewer.pick({ kind: "face", index: 0 });
    viewer.pick({ kind: "face", index: 2 }, true);
    await waitFor(() => {
      expect(region).toHaveTextContent("Closest points ≈2.50 mm");
    });
    expect(region).toHaveTextContent("Angle ≈90.0°");
    viewer.pick({ kind: "face", index: 1 }, true);
    expect(region).toBeEmptyDOMElement();
    viewer.pick({ kind: "part" });
    expect(region).toBeEmptyDOMElement();
  });

  it("never sends a measurement: the message carries the picked indices and nothing else", async () => {
    const viewer = new FakeViewer();
    viewer.reading = { distance: 65.28, angle: 0 };
    const { chat } = await open(viewer);
    viewer.pick({ kind: "face", index: 0 });
    viewer.pick({ kind: "face", index: 1 }, true);
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "make this taller{Enter}");
    await waitFor(() => {
      expect(chat.sent).toEqual(["make this taller"]);
    });
    expect(chat.picked).toEqual([{ variant_id: "v1", faces: [0, 1], edges: [], part: false }]);
  });
});

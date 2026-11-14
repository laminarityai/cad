import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import type { DoneCheck } from "@/api/snapshot";
import { FakeChat, FakeViewer, fakeApi } from "@/test/fakes";
import { massResult, snapshot } from "@/test/fixtures";
import { Workspace } from "./Workspace";

const PLATE = "polymaker-fiberon-pa6-cf20";
const GEAR = "cliffs-hot-rolled-cs-type-b";
const JOINTS = "How the bodies are joined is not checked.";
const AGENT = { kind: "agent_argument" as const, statement: "The agent chose this material." };
const meshNeverArrives = () => new Promise<never>(() => undefined);

const weighed = (gear: boolean): DoneCheck => ({
  ...massResult(),
  verdict: gear ? "pass" : "unknown",
  measured: [
    { name: "volume", value: { magnitude: 18_830, unit: "mm³" } },
    { name: "volume:plate", value: { magnitude: 12_800, unit: "mm³" } },
    { name: "mass:plate", value: { magnitude: 0.014976, unit: "kg" } },
    { name: "volume:gear", value: { magnitude: 6_030, unit: "mm³" } },
    ...(gear
      ? [
          { name: "mass:gear", value: { magnitude: 0.047456, unit: "kg" } },
          { name: "mass", value: { magnitude: 0.062432, unit: "kg" } },
        ]
      : []),
  ],
});

function bodied(gear: boolean) {
  return {
    ...snapshot("v1", [], [weighed(gear)]),
    material_key: null,
    material: null,
    bodies: [
      { name: "plate", solids: [0] },
      { name: "gear", solids: [1, 2] },
    ],
    body_materials: [
      { body: "plate", key: PLATE, set_by: AGENT },
      { body: "gear", key: GEAR, set_by: AGENT },
    ],
    untested: [JOINTS],
  };
}

async function open(gear: boolean) {
  const api = fakeApi(["v1"], {
    project: vi.fn(() =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] }),
    ),
    scorecard: vi.fn(() => Promise.resolve(bodied(gear))),
    mesh: vi.fn(meshNeverArrives),
    view: vi.fn((variantId: string) =>
      Promise.resolve({
        variant_id: variantId,
        brep_sha256: "b".repeat(64),
        mesh: "tessellated" as const,
        mesh_url: `/v1/geometry/0123456789ab/${variantId}.json`,
        areas: [
          { name: "plate", colour: "#1a1a1a", faces: [0, 1, 2, 3, 4, 5] },
          { name: "gear", colour: "#808080", faces: [6, 7, 8, 9, 10, 11] },
        ],
      }),
    ),
  });
  render(
    <ServicesProvider services={{ api, viewer: new FakeViewer(), chat: new FakeChat() }}>
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <Routes>
          <Route path="projects/:projectId" element={<Workspace />} />
        </Routes>
      </MemoryRouter>
    </ServicesProvider>,
  );
  return screen.findByRole("list", { name: "Bodies" });
}

const row = (list: HTMLElement, name: string) => {
  const found = list.querySelector(`[data-body="${name}"]`);
  if (!(found instanceof HTMLElement)) throw new Error(`the ${name} row is missing`);
  return found;
};

describe("the bodies of a variant", () => {
  it("each show their colour, material, who chose it, solids, and what the mass check measured of that body", async () => {
    const list = await open(true);
    const plate = row(list, "plate");
    expect(within(plate).getByText(`${PLATE} · chosen by the agent · 1 solid`)).toBeInTheDocument();
    expect(within(plate).getByText("12.8 cm³ · 15 g")).toBeInTheDocument();
    await waitFor(() => {
      expect(plate.querySelector("[data-swatch]")).toHaveStyle({ backgroundColor: "#1a1a1a" });
    });
    const gear = row(list, "gear");
    expect(within(gear).getByText(`${GEAR} · chosen by the agent · 2 solids`)).toBeInTheDocument();
    expect(within(gear).getByText("6.03 cm³ · 47.5 g")).toBeInTheDocument();
  });

  it("list how the bodies are joined as a line with no test yet", async () => {
    await open(true);
    const line = screen.getByText(JOINTS).closest("[data-line]");
    if (!(line instanceof HTMLElement)) throw new Error("the joints line is missing");
    expect(line).toHaveAttribute("data-line", "unchecked");
    expect(within(line).getByText("No test yet")).toBeInTheDocument();
  });

  it("never show a mass for the whole variant while one body's density is unknown", async () => {
    const list = await open(false);
    expect(within(row(list, "plate")).getByText("12.8 cm³ · 15 g")).toBeInTheDocument();
    expect(within(row(list, "gear")).getByText("6.03 cm³ · mass not measured")).toBeInTheDocument();
    const mass = screen.getByText("Mass").closest("[data-line]");
    if (!(mass instanceof HTMLElement)) throw new Error("the mass row is missing");
    expect(mass).toHaveAttribute("data-line", "unknown");
    expect(within(mass).queryByText(/ g$/)).not.toBeInTheDocument();
  });
});

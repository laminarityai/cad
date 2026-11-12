import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { restore } from "@/api/snapshot";
import { massResult, mass, snapshot } from "@/test/fixtures";
import { Checks } from "./bits";

const waiting = {
  kind: "awaiting" as const,
  label: "waiting for your Confirm, no verdict" as const,
  requirement_id: "r2",
  statement: "Mass at most 30 g",
  check_id: "mass",
  instance: "",
  values: [{ measure: "mass", proposed: { magnitude: 30, unit: "g" }, measured: { magnitude: 41.2, unit: "g" } }],
};

const assumed = {
  kind: "assumed" as const,
  label: "assumed by the agent, no verdict" as const,
  statement: "Hold 40 N at the far end",
  why: "a desk shelf",
  check_id: "fea",
  instance: "load-1",
  values: [],
};

describe("the Checks pane", () => {
  it("shows what you asked, what awaits your Confirm and what the agent assumed as three groups", () => {
    const wire = { ...snapshot("v1", [mass("pass")], [massResult()]), awaiting: [waiting], assumptions: [assumed] };
    render(<Checks card={{ snapshot: restore(wire) }} material={null} />);
    expect(screen.getAllByRole("heading", { level: 3 }).map((one) => one.textContent)).toEqual(["What you asked", "Awaiting your Confirm", "Assumed by the agent"]);
  });

  it("puts the measure beside the waiting target and gives it no verdict", () => {
    const wire = { ...snapshot("v1", [], [massResult()]), awaiting: [waiting] };
    const { container } = render(<Checks card={{ snapshot: restore(wire) }} material={null} />);
    const row = container.querySelector("[data-awaiting]");
    if (!(row instanceof HTMLElement)) throw new Error("the awaiting group is missing");
    expect(within(row).getByText("Mass at most 30 g")).toBeInTheDocument();
    expect(within(row).getByText("Waiting for you, no verdict yet")).toBeInTheDocument();
    expect(within(row).getByText("mass: 41.2 g, your target 30 g")).toBeInTheDocument();
    expect(within(row).queryByText(/Pass|Fail/)).not.toBeInTheDocument();
  });
});

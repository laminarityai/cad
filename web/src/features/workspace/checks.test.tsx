import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { restore } from "@/api/snapshot";
import { massResult, mass, snapshot } from "@/test/fixtures";
import { Checks } from "./bits";
import { summaryOf } from "./cards";

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

const LABEL = "agent-written check you approved, not reviewed by our team" as const;

function agentChecked(verdict: "pass" | "fail", strain: number) {
  return {
    kind: "agent_checked" as const,
    label: LABEL,
    requirement_id: "r3",
    statement: "Snap-fit strain is at most 2 %",
    check_sha256: "a".repeat(64),
    title: "Snap-fit strain",
    formula: "1.5 * h * y / l ** 2",
    version: "v",
    verdict,
    reason: verdict === "pass" ? "The agent-written check's value meets the limit you confirmed." : "The agent-written check's value does not meet the limit you confirmed.",
    value: { magnitude: strain, unit: "%" },
    comparator: "at_most" as const,
    limit: { magnitude: 2, unit: "%" },
    inputs: [],
    pages: ["https://example.com/snap-fit-guide"],
  };
}

describe("the Checks pane", () => {
  it("labels a verdict an agent-written check reached, pass or fail", () => {
    for (const [verdict, strain] of [["pass", 1.5], ["fail", 3]] as const) {
      const wire = snapshot("v1", [agentChecked(verdict, strain)], [massResult()]);
      const { container, unmount } = render(<Checks card={{ snapshot: restore(wire) }} material={null} />);
      const row = container.querySelector(`[data-line="${verdict === "pass" ? "agent" : "fail"}"]`);
      if (!(row instanceof HTMLElement)) throw new Error("the agent-written check's row is missing");
      expect(within(row).getByText(LABEL)).toBeInTheDocument();
      expect(within(row).getByText(`${String(strain)} %`)).toBeInTheDocument();
      unmount();
    }
  });

  it("counts an agent-written check's pass apart in the card summary", () => {
    const wire = snapshot("v1", [mass("pass"), agentChecked("pass", 1.5)], [massResult()]);
    expect(summaryOf({ snapshot: restore(wire) })).toEqual({ status: "agent", text: "All pass, 1 on the agent's check" });
  });

  it("labels a verdict on a load case the agent described, and counts it apart in the summary", () => {
    const described = { ...mass("pass"), check_id: "fea", requirement_id: "r5", statement: "Holds 49 N", load_case: "described" as const };
    const wire = snapshot("v1", [described], [massResult()]);
    const { container } = render(<Checks card={{ snapshot: restore(wire) }} material={null} />);
    const row = container.querySelector('[data-line="pass"]');
    if (!(row instanceof HTMLElement)) throw new Error("the described row is missing");
    expect(within(row).getByText("load case the agent described, not reviewed by our team")).toBeInTheDocument();
    expect(summaryOf({ snapshot: restore(wire) })).toEqual({ status: "pass", text: "All pass, 1 on a load case the agent described" });
  });

  it("leaves a reviewed load case with no label", () => {
    const wire = snapshot("v1", [mass("pass")], [massResult()]);
    const { container } = render(<Checks card={{ snapshot: restore(wire) }} material={null} />);
    expect(container.querySelector("[data-tag]")).toBeNull();
  });

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

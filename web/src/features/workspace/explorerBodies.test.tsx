import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Explorer } from "./Explorer";
import type { Brief } from "./model";

const bodies = [
  { name: "plate", material: "polymaker-fiberon-pa6-cf20", chosenBy: "agent" as const },
  { name: "gear", material: "cliffs-hot-rolled-cs-type-b", chosenBy: "you" as const },
];
const brief = (slotBodies: typeof bodies): Brief => ({
  id: "b1",
  words: "a gear plate",
  title: "Gear plate",
  state: "ready",
  slots: [{ slot: 1, label: "Option 1", differs: "", revisions: [{ n: 1, variantId: "v1", at: "2026-11-10T00:00:00Z" }], bodies: slotBodies }],
  materialOf: {},
  fits: [],
});

function open(slotBodies: typeof bodies, bodyOf: Record<string, string | null> = {}) {
  const dispatch = vi.fn();
  render(
    <Explorer
      projectId="p1"
      briefs={[brief(slotBodies)]}
      current="b1"
      slot={1}
      bodyOf={bodyOf}
      cards={{}}
      parts={[]}
      documents={[]}
      sources={[]}
      dispatch={dispatch}
      onNew={vi.fn()}
      onChanged={vi.fn()}
      working={null}
    />,
  );
  return dispatch;
}

describe("the explorer's bodies", () => {
  it("lists each body of an option by name with its material, and lists none for one unnamed body", () => {
    open(bodies);
    const plate = screen.getByRole("button", { name: /^plate/ });
    expect(within(plate).getByText("polymaker-fiberon-pa6-cf20")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^gear/ })).toBeInTheDocument();
  });

  it("lists no body row for an option of one unnamed body", () => {
    open([]);
    expect(document.querySelector("[data-body-node]")).toBeNull();
  });

  it("shows one body alone on a click, and the whole model again on a second click on it", async () => {
    const dispatch = open(bodies);
    await userEvent.click(screen.getByRole("button", { name: /^gear/ }));
    expect(dispatch).toHaveBeenCalledWith({ type: "brief", briefId: "b1" });
    expect(dispatch).toHaveBeenCalledWith({ type: "slot", briefId: "b1", slot: 1 });
    expect(dispatch).toHaveBeenLastCalledWith({ type: "body", key: "b1:1", body: "gear" });
  });

  it("marks the body shown alone, and a click on it puts the whole model back", async () => {
    const dispatch = open(bodies, { "b1:1": "gear" });
    const gear = screen.getByRole("button", { name: /^gear/ });
    expect(gear).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /^plate/ })).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(gear);
    expect(dispatch).toHaveBeenLastCalledWith({ type: "body", key: "b1:1", body: null });
  });
});

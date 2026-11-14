import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Refused } from "@/api/client";
import { FakeChat } from "@/test/fakes";
import { feaPending, massResult, snapshot } from "@/test/fixtures";
import { mountWorkspace as mount } from "@/test/workspace";

describe("the checks of an option", () => {
  const checks = () => screen.findByRole("region", { name: "Checks" });

  it("says an option nobody scored is not checked yet, with nothing moving", async () => {
    const notScored = vi.fn(() => Promise.reject(new Refused(400, "NotScored: variant v1 has no stored check result", "NotScored")));
    mount(new FakeChat(), ["v1"], null, notScored);
    const pane = await checks();
    expect(await within(pane).findByText("Not checked yet.")).toBeInTheDocument();
    expect(pane.querySelector("[data-spinner], [data-shimmer]")).toBeNull();
    expect(within(pane).queryByText(/Checking/)).toBeNull();
  });

  it("says the checks could not be read when the read fails another way, with nothing moving", async () => {
    mount(new FakeChat(), ["v1"], null, vi.fn(() => Promise.reject(new Error("down"))));
    const pane = await checks();
    expect(await within(pane).findByText("The checks could not be read.")).toBeInTheDocument();
    expect(pane.querySelector("[data-spinner], [data-shimmer]")).toBeNull();
  });

  it("stops every check spinner and says the server is not answering when a later read fails", async () => {
    const running = snapshot("v1", [], [massResult(), feaPending()]);
    const scorecard = vi.fn().mockResolvedValueOnce(running).mockRejectedValue(new Error("down"));
    mount(new FakeChat(), ["v1"], null, scorecard);
    const pane = await checks();
    const explorer = screen.getByRole("region", { name: "Explorer" });
    const tabs = screen.getByRole("tablist", { name: "Options" });
    await waitFor(() => {
      expect(pane.querySelector("[data-spinner]")).not.toBeNull();
    });
    expect(tabs.querySelector("[data-spinner]")).not.toBeNull();
    await waitFor(
      () => {
        expect(within(pane).getByText("Not answering")).toBeInTheDocument();
      },
      { timeout: 4000 },
    );
    expect(document.querySelector("[data-spinner]")).toBeNull();
    expect(within(pane).queryByText("Checking")).toBeNull();
    expect(within(tabs).getByRole("img", { name: "Not answering" })).toBeInTheDocument();
    expect(within(explorer).getByRole("img", { name: "Not answering" })).toBeInTheDocument();
  });

  it("says it is reading them while the first read has not answered", async () => {
    mount(new FakeChat(), ["v1"], null, vi.fn(() => new Promise<never>(() => undefined)));
    const pane = await checks();
    expect(await within(pane).findByText("Reading the checks")).toBeInTheDocument();
    expect(pane.querySelector("[data-spinner]")).toBeNull();
    expect(within(pane).queryByText(/once an option is built/)).toBeNull();
  });
});

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FakeChat, runningRun } from "@/test/fakes";
import { mountWorkspace as mount } from "@/test/workspace";
import { RunStatus } from "./RunStatus";
import { viewOf } from "./run";

const view = (checksSettling: boolean) => {
  const run = viewOf(runningRun(1));
  return run.status === "running" ? { ...run, checksSettling } : run;
};

const shown = (checksSettling: boolean) =>
  render(<RunStatus run={view(checksSettling)} working={null} stalled={false} problem={null} onStop={() => undefined} />);

describe("the Auto run line between turns", () => {
  it("says its checks are still running when the server reports them settling", () => {
    shown(true);
    expect(screen.getByText(/Its checks are still running/)).toBeInTheDocument();
    expect(screen.queryByText(/Nothing is working/)).toBeNull();
  });

  it("says nothing works on it when no check is left", () => {
    shown(false);
    expect(screen.getByText(/Nothing is working on it now/)).toBeInTheDocument();
  });
});

describe("the one line a long conversation shows", () => {
  it("draws the stored notice once, in the chat", async () => {
    const chat = new FakeChat();
    chat.say({ kind: "user", text: "go", selection: null });
    chat.say({ kind: "context_trimmed", text: "This conversation is long. The agent no longer sees the full results of its earliest steps." });
    chat.say({ kind: "turn_ended" });
    mount(chat, ["v1"]);
    const notice = await screen.findByText(/This conversation is long/, undefined, { timeout: 6000 });
    expect(notice).toHaveAttribute("data-said", "notice");
    expect(screen.getAllByText(/This conversation is long/)).toHaveLength(1);
  });
});

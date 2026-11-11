import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { Workspace } from "@/workspace/Workspace";
import { FakeChat, FakeEvents, FakeViewer, fakeApi, runningRun, stoppedRun } from "@/test/fakes";
import type { Mode } from "@/api/types";
import { nextMode } from "./modes";
import { CONVERSATION_FOLLOW_MS } from "./useAuto";

function mount(chat: FakeChat, mode: Mode | null = null) {
  if (mode !== null) chat.mode = mode;
  const api = fakeApi(["v1"], {
    project: vi.fn(() =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [] }),
    ),
  });
  return render(
    <ServicesProvider services={{ api, events: new FakeEvents(), viewer: new FakeViewer(), chat }}>
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <Routes>
          <Route path="projects/:projectId" element={<Workspace />} />
        </Routes>
      </MemoryRouter>
    </ServicesProvider>,
  );
}

const picker = () => screen.findByRole("button", { name: /^Mode:/ });

async function choose(label: "Plan" | "Design" | "Auto") {
  await userEvent.click(await picker());
  await userEvent.click(await screen.findByRole("menuitemradio", { name: new RegExp(`^${label}`) }));
}

function autoRunning(chat: FakeChat) {
  chat.mode = "auto";
  chat.autoRun = runningRun(2);
  chat.say({ kind: "tool_call", call_id: "a", name: "auto_start", input: {} });
  chat.say({ kind: "tool_result", call_id: "a", text: JSON.stringify(runningRun(2)), is_error: false });
}

describe("mode switcher", () => {
  it("offers Plan, Design and Auto and sends the one picked", async () => {
    const chat = new FakeChat();
    mount(chat);
    await choose("Design");
    await choose("Auto");
    await choose("Plan");
    expect(chat.modes).toEqual(["design", "auto", "plan"]);
    await waitFor(async () => {
      expect(await picker()).toHaveAttribute("data-mode", "plan");
    });
  });

  it("shows the mode the server holds, not the one asked for", async () => {
    const chat = new FakeChat();
    chat.setMode.mockImplementationOnce((conversationId: string) => {
      chat.mode = "design";
      return Promise.resolve({ conversation_id: conversationId, mode: "design", auto_run: null });
    });
    mount(chat);
    await choose("Auto");
    await waitFor(async () => {
      expect(await picker()).toHaveAttribute("data-mode", "design");
    });
  });

  it("moves to the next mode on Shift+Tab in the input, and wraps", async () => {
    const chat = new FakeChat();
    mount(chat, "design");
    await userEvent.type(await screen.findByRole("textbox", { name: "Message" }), "{Shift>}{Tab}{/Shift}");
    await waitFor(async () => {
      expect(await picker()).toHaveAttribute("data-mode", "auto");
    });
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "{Shift>}{Tab}{/Shift}");
    expect(chat.modes).toEqual(["auto", "plan"]);
    expect([nextMode("plan"), nextMode("design"), nextMode("auto"), nextMode(null)]).toEqual(["design", "auto", "plan", "plan"]);
  });

  it("asks for what the person needs in Plan and for a change after it", async () => {
    const chat = new FakeChat();
    mount(chat);
    expect(await screen.findByPlaceholderText("Describe what you need")).toBeInTheDocument();
    await choose("Design");
    expect(await screen.findByPlaceholderText(/Ask for a change, such as/)).toBeInTheDocument();
  });

  it("says why the server refused a switch", async () => {
    const chat = new FakeChat();
    chat.setMode.mockRejectedValueOnce(new Error("the mode was not changed"));
    mount(chat);
    await choose("Auto");
    expect(await screen.findByRole("alert")).toHaveTextContent("the mode was not changed");
  });
});

describe("Auto run status", () => {
  it("shows nothing outside Auto, then a running run with a Stop button", async () => {
    const chat = new FakeChat();
    mount(chat);
    await picker();
    expect(screen.queryByRole("region", { name: "Auto run" })).not.toBeInTheDocument();
    autoRunning(chat);
    const status = await screen.findByRole("region", { name: "Auto run" }, { timeout: CONVERSATION_FOLLOW_MS + 2000 });
    expect(status).toHaveTextContent("Running · 2 revisions tried");
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
  });

  it("stops the run, says the person stopped it, and moves the switcher to Design", async () => {
    const chat = new FakeChat();
    chat.say({ kind: "user", text: "go", selection: null });
    autoRunning(chat);
    mount(chat, "auto");
    await userEvent.click(await screen.findByRole("button", { name: "Stop" }));
    expect(chat.stops).toEqual(["run_1"]);
    const status = await screen.findByRole("region", { name: "Auto run" });
    await waitFor(() => {
      expect(status).toHaveTextContent("Stopped · you stopped it");
    });
    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
    expect(await picker()).toHaveAttribute("data-mode", "design");
  });

  it("stops the run when the person leaves Auto", async () => {
    const chat = new FakeChat();
    autoRunning(chat);
    mount(chat, "auto");
    await screen.findByRole("button", { name: "Stop" });
    await choose("Design");
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Auto run" })).toHaveTextContent("Stopped · you stopped it");
    });
    expect(chat.modes).toEqual(["design"]);
  });

  it("moves to Design and shows the server's reason and report when a run stops on its own", async () => {
    const chat = new FakeChat();
    autoRunning(chat);
    mount(chat, "auto");
    await screen.findByRole("button", { name: "Stop" });
    chat.stopsItself("all_pass", "Every checked requirement passes.");
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Auto run" })).toHaveTextContent("Stopped · every checked requirement passes");
    });
    expect(await picker()).toHaveAttribute("data-mode", "design");
    expect(screen.getByText("Every checked requirement passes.")).toBeInTheDocument();
    expect(screen.getByText("Auto stopped · every checked requirement passes")).toBeInTheDocument();
  });

  it("names each stop reason in the chat, including the account limit", async () => {
    const chat = new FakeChat();
    autoRunning(chat);
    mount(chat, "auto");
    await screen.findByRole("button", { name: "Stop" });
    chat.stopsItself("account_limit", "The account's limit was reached.");
    expect(await screen.findByText("Auto stopped · the account limit halted it")).toBeInTheDocument();
  });

  it("keeps the mode and the run across a reload", async () => {
    const chat = new FakeChat();
    const first = mount(chat, "auto");
    autoRunning(chat);
    await screen.findByRole("button", { name: "Stop" });
    chat.stopsItself("needs_person", "A requirement waits on you.");
    await waitFor(async () => {
      expect(await picker()).toHaveAttribute("data-mode", "design");
    });
    first.unmount();

    mount(chat);
    await waitFor(async () => {
      expect(await picker()).toHaveAttribute("data-mode", "design");
    });
    expect(screen.getByRole("region", { name: "Auto run" })).toHaveTextContent("Stopped · it needs you");
    await choose("Auto");
    expect(chat.modes).toEqual(["auto"]);
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Auto run" })).toHaveTextContent("No run yet");
    });
  });

  it("shows a stop pressed in another tab within one follow, with no reload", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const chat = new FakeChat();
      autoRunning(chat);
      mount(chat, "auto");
      await screen.findByRole("button", { name: "Stop" });
      chat.mode = "design";
      chat.autoRun = stoppedRun("run_1", "stopped_by_person", "You stopped the run.");
      await act(() => vi.advanceTimersByTimeAsync(CONVERSATION_FOLLOW_MS));
      await waitFor(() => {
        expect(screen.getByRole("region", { name: "Auto run" })).toHaveTextContent("Stopped · you stopped it");
      });
      expect(await picker()).toHaveAttribute("data-mode", "design");
      expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows the run and its Stop button on the chat tab of a narrow screen", async () => {
    const real = window.matchMedia.bind(window);
    window.matchMedia = (query: string) => Object.assign(real(query), { matches: true });
    try {
      const chat = new FakeChat();
      mount(chat, "auto");
      autoRunning(chat);
      await userEvent.click(await screen.findByRole("button", { name: "Chat" }));
      await userEvent.click(await screen.findByRole("button", { name: "Stop" }, { timeout: CONVERSATION_FOLLOW_MS + 2000 }));
      expect(chat.stops).toHaveLength(1);
    } finally {
      window.matchMedia = real;
    }
  });
});

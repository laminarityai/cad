import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { Workspace } from "@/features/workspace/Workspace";
import { FakeChat, FakeViewer, fakeApi, runningRun, stoppedRun } from "@/test/fakes";
import { CONVERSATION_FOLLOW_MS } from "./useAuto";

function mount(chat: FakeChat) {
  const api = fakeApi(["v1"], {
    project: vi.fn(() =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] }),
    ),
  });
  return render(
    <ServicesProvider services={{ api, viewer: new FakeViewer(), chat }}>
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <Routes>
          <Route path="projects/:projectId" element={<Workspace />} />
        </Routes>
      </MemoryRouter>
    </ServicesProvider>,
  );
}

function autoRunning(chat: FakeChat) {
  chat.autoRun = runningRun(2);
  chat.say({ kind: "tool_call", call_id: "a", name: "auto_start", input: {} });
  chat.say({ kind: "tool_result", call_id: "a", text: JSON.stringify(runningRun(2)), is_error: false });
}

const status = () => screen.getByRole("region", { name: "Auto run" });

describe("Auto run status", () => {
  it("shows nothing before a run and offers no mode, then a running run with a Stop button", async () => {
    const chat = new FakeChat();
    mount(chat);
    expect(await screen.findByPlaceholderText(/Ask for a change, such as/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Auto run" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Mode/ })).not.toBeInTheDocument();
    autoRunning(chat);
    const shown = await screen.findByRole("region", { name: "Auto run" }, { timeout: CONVERSATION_FOLLOW_MS + 2000 });
    expect(shown).toHaveTextContent("Running · 2 revisions tried");
    expect(screen.getByRole("button", { name: "Stop" })).toBeInTheDocument();
  });

  it("stops the run and says the person stopped it", async () => {
    const chat = new FakeChat();
    chat.say({ kind: "user", text: "go", selection: null });
    autoRunning(chat);
    mount(chat);
    await userEvent.click(await screen.findByRole("button", { name: "Stop" }));
    expect(chat.stops).toEqual(["run_1"]);
    await waitFor(() => {
      expect(status()).toHaveTextContent("Stopped · you stopped it");
    });
    expect(screen.queryByRole("button", { name: "Stop" })).not.toBeInTheDocument();
  });

  it("shows the server's reason and report when a run stops on its own", async () => {
    const chat = new FakeChat();
    autoRunning(chat);
    mount(chat);
    await screen.findByRole("button", { name: "Stop" });
    chat.stopsItself("all_pass", "Every checked requirement passes.");
    await waitFor(() => {
      expect(status()).toHaveTextContent("Stopped · every checked requirement passes");
    });
    expect(screen.getByText("Every checked requirement passes.")).toBeInTheDocument();
    expect(screen.getByText("Auto stopped · every checked requirement passes")).toBeInTheDocument();
  });

  it("names each stop reason in the chat, including the account limit", async () => {
    const chat = new FakeChat();
    autoRunning(chat);
    mount(chat);
    await screen.findByRole("button", { name: "Stop" });
    chat.stopsItself("account_limit", "The account's limit was reached.");
    expect(await screen.findByText("Auto stopped · the account limit halted it")).toBeInTheDocument();
  });

  it("keeps a stopped run across a reload until the person's next message lifts it", async () => {
    const chat = new FakeChat();
    const first = mount(chat);
    autoRunning(chat);
    await screen.findByRole("button", { name: "Stop" });
    chat.stopsItself("needs_person", "A requirement waits on you.");
    await waitFor(() => {
      expect(status()).toHaveTextContent("Stopped · it needs you");
    });
    first.unmount();

    mount(chat);
    await waitFor(() => {
      expect(status()).toHaveTextContent("Stopped · it needs you");
    });
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "make it lighter{Enter}");
    await waitFor(
      () => {
        expect(screen.queryByRole("region", { name: "Auto run" })).not.toBeInTheDocument();
      },
      { timeout: CONVERSATION_FOLLOW_MS + 2000 },
    );
    expect(screen.getByText("A requirement waits on you.")).toBeInTheDocument();
  });

  it("shows a stop pressed in another tab within one follow, with no reload", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const chat = new FakeChat();
      autoRunning(chat);
      mount(chat);
      await screen.findByRole("button", { name: "Stop" });
      chat.autoRun = stoppedRun("run_1", "stopped_by_person", "You stopped the run.");
      chat.stoppedRun = "run_1";
      await act(() => vi.advanceTimersByTimeAsync(CONVERSATION_FOLLOW_MS));
      await waitFor(() => {
        expect(status()).toHaveTextContent("Stopped · you stopped it");
      });
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
      mount(chat);
      autoRunning(chat);
      await userEvent.click(await screen.findByRole("tab", { name: "Chat" }));
      await userEvent.click(await screen.findByRole("button", { name: "Stop" }, { timeout: CONVERSATION_FOLLOW_MS + 2000 }));
      expect(chat.stops).toHaveLength(1);
    } finally {
      window.matchMedia = real;
    }
  });
});

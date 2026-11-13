import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { Gate } from "@/components/Gate";
import { FakeChat, FakeViewer, fakeApi, runningRun, setOf } from "@/test/fakes";
import { ChatPane } from "./Chat";
import { Workspace } from "./Workspace";

function mount(chat: FakeChat, members: string[]) {
  const api = fakeApi(members, {
    project: vi.fn(() =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] }),
    ),
    variantSet: vi.fn(() => Promise.resolve(setOf(members))),
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

const say = (chat: FakeChat, ...events: Parameters<FakeChat["say"]>[0][]) => {
  act(() => {
    for (const event of events) chat.say(event);
  });
};

describe("a brief with no options", () => {
  it("says there are none, and never says it is building, when nothing runs", async () => {
    mount(new FakeChat(), []);
    expect((await screen.findAllByText(/No options yet/)).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Building/)).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("region", { name: "Chat" })).toHaveAttribute("aria-busy", "false");
  });

  it("shows the work only while a turn runs, and drops it when the turn ends", async () => {
    const chat = new FakeChat();
    mount(chat, []);
    await screen.findAllByText(/No options yet/);
    say(chat, { kind: "user", text: "a hook", selection: null }, { kind: "tool_call", call_id: "a", name: "build_variant", input: { label: "Wide base", slot: 1 } });
    const centre = (await screen.findAllByRole("status")).filter((one) => /^Building an option/.test(one.textContent));
    expect(centre.length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/No options yet/)).toBeNull();
    expect(screen.getByRole("region", { name: "Chat" })).toHaveAttribute("aria-busy", "true");
    say(chat, { kind: "tool_result", call_id: "a", text: "{}", is_error: false }, { kind: "agent", text: "Built." }, { kind: "turn_ended" });
    await waitFor(() => {
      expect(screen.queryByRole("status")).toBeNull();
    });
    expect(screen.getAllByText(/No options yet/).length).toBeGreaterThan(0);
    expect(screen.getByRole("region", { name: "Chat" })).toHaveAttribute("aria-busy", "false");
  });
});

describe("the tool rows in the chat", () => {
  it("shows one row for each call, with what it worked on, running until its result comes", async () => {
    const chat = new FakeChat();
    mount(chat, ["v1"]);
    await screen.findByPlaceholderText(/Ask for a change, such as/);
    say(
      chat,
      { kind: "user", text: "build", selection: null },
      { kind: "tool_call", call_id: "a", name: "build_variant", input: { label: "Wide base", slot: 1, code: "x".repeat(500) } },
      { kind: "tool_call", call_id: "b", name: "score_variant", input: { variant_id: "v1" } },
    );
    const log = screen.getByRole("log");
    const rows = await within(log).findAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveAttribute("data-tool", "running");
    expect(within(rows[0] as HTMLElement).getByText("Wide base")).toBeInTheDocument();
    say(chat, { kind: "tool_result", call_id: "a", text: "{}", is_error: false }, { kind: "tool_result", call_id: "b", text: "refused", is_error: true });
    say(chat, { kind: "turn_ended" });
    await userEvent.click(await screen.findByRole("button", { name: "Built, checked" }));
    await waitFor(() => {
      expect(within(log).getAllByRole("listitem")[0]).toHaveAttribute("data-tool", "done");
    });
    expect(within(log).getAllByRole("listitem")[1]).toHaveAttribute("data-tool", "refused");
    expect(within(log).queryByText("xxxxx")).toBeNull();
  });

  it("shows the inputs of a call when its row opens, and never its code", async () => {
    render(
      <ChatPane
        lines={[{ seq: 1, kind: "tool", callId: "a", name: "build_variant", input: { label: "Wide base", slot: 2, code: "secret_code()" }, result: { text: "{}", isError: false } }]}
        working={null}
        card={null}
        composer={null}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /Built/ }));
    await userEvent.click(await screen.findByRole("button", { name: /Built\s*Wide base/ }));
    expect(await screen.findByText("slot: 2")).toBeInTheDocument();
    expect(screen.queryByText(/secret_code/)).toBeNull();
  });
});

describe("the Auto run line", () => {
  it("shows the run as working while it runs, even between turns", async () => {
    const chat = new FakeChat();
    chat.say({ kind: "user", text: "go", selection: null });
    chat.autoRun = runningRun(1);
    chat.say({ kind: "tool_call", call_id: "a", name: "auto_start", input: {} });
    chat.say({ kind: "tool_result", call_id: "a", text: JSON.stringify(chat.autoRun), is_error: false });
    chat.say({ kind: "turn_ended" });
    mount(chat, ["v1"]);
    const run = await screen.findByRole("region", { name: "Auto run" }, { timeout: 6000 });
    expect(within(run).getByRole("status")).toHaveTextContent("Running · 1 revision tried");
    expect(screen.getByRole("region", { name: "Chat" })).toHaveAttribute("aria-busy", "true");
  });
});

describe("a request that is open", () => {
  it("shows the loading label for screen readers while it loads and the page when it is done", () => {
    const { rerender } = render(<Gate resource={{ status: "loading" }}>{() => <p>ready</p>}</Gate>);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    rerender(<Gate resource={{ status: "ok", data: 1 }}>{() => <p>ready</p>}</Gate>);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByText("ready")).toBeInTheDocument();
  });
});

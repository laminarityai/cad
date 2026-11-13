import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { Gate } from "@/components/Gate";
import { Refused, type Api } from "@/api/client";
import { FakeChat, FakeViewer, fakeApi, runningRun, setOf } from "@/test/fakes";
import { brief } from "@/test/fixtures";
import { ChatPane } from "./Chat";
import { Workspace } from "./Workspace";

const briefOn = (id: string) => ({ brief_id: id, created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 });

function mount(chat: FakeChat, members: string[], emptyBrief: string | null = null, scorecard?: Api["scorecard"]) {
  const briefs = emptyBrief === null ? [briefOn("b1")] : [briefOn(emptyBrief), briefOn("b1")];
  const api = fakeApi(members, {
    ...(scorecard ? { scorecard } : {}),
    project: vi.fn(() => Promise.resolve({ project_id: "p1", briefs, context_parts: [], documents: [] })),
    brief: vi.fn((briefId: string) => Promise.resolve({ ...brief(true), brief_id: briefId })),
    variantSet: vi.fn((_project: string, briefId: string) => Promise.resolve(setOf(briefId === emptyBrief ? [] : members))),
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
    say(chat, { kind: "user", text: "a hook", selection: null }, { kind: "tool_call", call_id: "a", name: "build_variant", input: { brief_id: "b1", label: "Wide base", slot: 1 } });
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
    await userEvent.click(await screen.findByRole("button", { name: "Built, 1 refused" }));
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

describe("a tool row while its call runs", () => {
  it("says what it is doing now, and says it is done only when the result comes", async () => {
    const chat = new FakeChat();
    mount(chat, ["v1"]);
    await screen.findByPlaceholderText(/Ask for a change, such as/);
    say(
      chat,
      { kind: "user", text: "build", selection: null },
      { kind: "tool_call", call_id: "s", name: "create_brief", input: {} },
      { kind: "tool_result", call_id: "s", text: "{}", is_error: false },
      { kind: "tool_call", call_id: "a", name: "build_variant", input: { label: "Slim base", slot: 1 } },
    );
    const log = screen.getByRole("log");
    const row = (await within(log).findAllByRole("listitem"))[1] as HTMLElement;
    expect(row).toHaveTextContent("Building an option");
    expect(row).not.toHaveTextContent(/Built/);
    expect(within(log).queryByText(/built/i)).toBeNull();
    say(chat, { kind: "tool_result", call_id: "a", text: "{}", is_error: false });
    await waitFor(() => {
      expect(within(log).getAllByRole("listitem")[1]).toHaveTextContent("Built");
    });
  });
});

describe("a turn the server cut off", () => {
  it("shows no work and says the call did not finish", async () => {
    const chat = new FakeChat();
    chat.say({ kind: "user", text: "a hook", selection: null });
    chat.say({ kind: "tool_call", call_id: "a", name: "build_variant", input: { label: "Wide base", slot: 1 } });
    chat.say({ kind: "turn_failed", message: "The server stopped before this turn finished. Send a message to carry on." });
    chat.say({ kind: "turn_ended" });
    mount(chat, []);
    expect(await screen.findByText(/Send a message to carry on/)).toBeInTheDocument();
    expect(screen.queryByText(/Building/)).toBeNull();
    expect(screen.queryByRole("status")).toBeNull();
    expect(document.querySelector("[data-spinner]")).toBeNull();
    expect(screen.getByRole("region", { name: "Chat" })).toHaveAttribute("aria-busy", "false");
    await userEvent.click(screen.getByRole("button", { name: /did not finish/ }));
    expect(within(screen.getByRole("log")).getByRole("listitem")).toHaveTextContent("did not finish");
  });
});

describe("an empty brief while another brief is worked on", () => {
  it("says it has no options, and only the brief the work is on says what is being done", async () => {
    const chat = new FakeChat();
    chat.briefId = null;
    mount(chat, ["v1"], "b0");
    const explorer = await screen.findByRole("region", { name: "Explorer" });
    await within(explorer).findByText("No options yet");
    say(chat, { kind: "user", text: "another", selection: null }, { kind: "tool_call", call_id: "a", name: "build_variant", input: { brief_id: "b1", label: "Slim base", slot: 2 } });
    await screen.findAllByText(/Building an option/);
    expect(within(explorer).queryByText(/Building/)).toBeNull();
    expect(within(explorer).getByText("No options yet")).toBeInTheDocument();
  });

  it("says it has no options while a turn only answers a question, though the conversation is bound to it", async () => {
    const chat = new FakeChat();
    chat.briefId = "b0";
    mount(chat, ["v1"], "b0");
    const explorer = await screen.findByRole("region", { name: "Explorer" });
    await within(explorer).findByText("No options yet");
    say(chat, { kind: "user", text: "what is PETG?", selection: null });
    await waitFor(() => {
      expect(screen.getByRole("region", { name: "Chat" })).toHaveAttribute("aria-busy", "true");
    });
    expect(within(explorer).queryByRole("status")).toBeNull();
    expect(within(explorer).getByText("No options yet")).toBeInTheDocument();
  });

  it("puts no work on an earlier brief of the turn while a new part is started", async () => {
    const chat = new FakeChat();
    mount(chat, ["v1"], "b0");
    const explorer = await screen.findByRole("region", { name: "Explorer" });
    await within(explorer).findByText("No options yet");
    say(
      chat,
      { kind: "user", text: "a lid too", selection: null },
      { kind: "tool_call", call_id: "a", name: "propose_requirements", input: { brief_id: "b0" } },
      { kind: "tool_result", call_id: "a", text: "{}", is_error: false },
      { kind: "tool_call", call_id: "b", name: "create_brief", input: {} },
    );
    await screen.findAllByText(/Starting the part/);
    expect(within(explorer).queryByRole("status")).toBeNull();
    expect(within(explorer).getByText("No options yet")).toBeInTheDocument();
  });
});

describe("the chat while the server does not answer", () => {
  it("shows no work, and says the server is not answering and the page is reconnecting", async () => {
    const chat = new FakeChat();
    mount(chat, ["v1"]);
    await userEvent.type(await screen.findByRole("textbox", { name: "Message" }), "build{Enter}");
    say(chat, { kind: "tool_call", call_id: "a", name: "build_variant", input: { label: "Wide base", slot: 1 } });
    const pane = screen.getByRole("region", { name: "Chat" });
    await waitFor(() => {
      expect(pane).toHaveAttribute("aria-busy", "true");
    });
    act(() => {
      chat.drop();
    });
    expect(await within(pane).findByText(/The server is not answering\. The page is reconnecting\./)).toBeInTheDocument();
    expect(pane).toHaveAttribute("aria-busy", "false");
    expect(document.querySelector("[data-loading]")).toBeNull();
    expect(pane.querySelector("[data-spinner]")).toBeNull();
    expect(within(pane).queryByText(/Building an option/)).toBeNull();
    expect(within(pane).queryByText(/\ds$/)).toBeNull();
  });
});

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

  it("says it is reading them while the first read has not answered", async () => {
    mount(new FakeChat(), ["v1"], null, vi.fn(() => new Promise<never>(() => undefined)));
    const pane = await checks();
    expect(await within(pane).findByText("Reading the checks")).toBeInTheDocument();
    expect(pane.querySelector("[data-spinner]")).toBeNull();
    expect(within(pane).queryByText(/once an option is built/)).toBeNull();
  });
});

const failedBuild = JSON.stringify({ outcome: { kind: "build_failed", error: "NameError", traceback: "" }, output: "", variant_id: "v2" });

describe("a build that failed", () => {
  it("says the build failed in its row and in the count, and never says it was built", async () => {
    const chat = new FakeChat();
    mount(chat, ["v1"]);
    await screen.findByPlaceholderText(/Ask for a change, such as/);
    say(
      chat,
      { kind: "user", text: "build", selection: null },
      { kind: "tool_call", call_id: "a", name: "build_variant", input: { label: "Wide base", slot: 1 } },
      { kind: "tool_result", call_id: "a", text: failedBuild, is_error: false },
      { kind: "tool_call", call_id: "b", name: "auto_revise", input: { slot: 1 } },
      { kind: "tool_result", call_id: "b", text: JSON.stringify({ ...runningRun(0), state: { ...runningRun(0).state, history: [{ revision: 1, variant_id: "v3", code_sha256: "e".repeat(64), built: false, marks: [] }] } }), is_error: false },
      { kind: "turn_ended" },
    );
    const log = screen.getByRole("log");
    await userEvent.click(await within(log).findByRole("button", { name: "2 builds failed" }));
    const rows = within(log).getAllByRole("listitem");
    expect(rows.map((one) => one.getAttribute("data-tool"))).toEqual(["failed", "failed"]);
    expect(rows[0]).toHaveTextContent("Build failed");
    expect(within(log).queryByText(/Built/)).toBeNull();
  });

  it("never says built when the result was cut too long to read", async () => {
    const chat = new FakeChat();
    mount(chat, ["v1"]);
    await screen.findByPlaceholderText(/Ask for a change, such as/);
    say(
      chat,
      { kind: "user", text: "build", selection: null },
      { kind: "tool_call", call_id: "a", name: "build_variant", input: { label: "Wide base", slot: 1 } },
      { kind: "tool_result", call_id: "a", text: `${failedBuild.slice(0, 40)}\n[cut: 9 more characters]`, is_error: false },
      { kind: "turn_ended" },
    );
    const log = screen.getByRole("log");
    await userEvent.click(await within(log).findByRole("button", { name: "Build finished" }));
    expect(within(log).getByRole("listitem")).toHaveTextContent("Build finished");
    expect(within(log).queryByText(/Built/)).toBeNull();
  });
});

describe("the clock", () => {
  it("counts from when the person sent the message", async () => {
    const chat = new FakeChat();
    mount(chat, ["v1"]);
    await userEvent.type(await screen.findByRole("textbox", { name: "Message" }), "build{Enter}");
    const working = await screen.findByText("Working");
    expect(working.closest("[role=status]")).toHaveTextContent(/0s$/);
  });

  it("is not shown for a turn whose start the page did not see", async () => {
    const chat = new FakeChat();
    chat.say({ kind: "user", text: "a hook", selection: null });
    mount(chat, ["v1"]);
    const working = await screen.findByText("Working");
    expect(working.closest("[role=status]")).not.toHaveTextContent(/\ds$/);
  });
});

function idleRun(): FakeChat {
  const chat = new FakeChat();
  chat.say({ kind: "user", text: "go", selection: null });
  chat.autoRun = runningRun(1);
  chat.say({ kind: "tool_call", call_id: "a", name: "auto_start", input: {} });
  chat.say({ kind: "tool_result", call_id: "a", text: JSON.stringify(chat.autoRun), is_error: false });
  chat.say({ kind: "turn_ended" });
  return chat;
}

describe("the Auto run line", () => {
  it("says nothing works on a running run between turns, and shows no loader or clock", async () => {
    mount(idleRun(), ["v1"]);
    const run = await screen.findByRole("region", { name: "Auto run" }, { timeout: 6000 });
    expect(run).toHaveTextContent("1 revision tried");
    expect(run).toHaveTextContent("Nothing is working on it now. Send a message to carry it on, or stop it.");
    expect(document.querySelector("[data-loading]")).toBeNull();
    expect(screen.queryByText(/Auto run working/)).toBeNull();
    expect(screen.getByRole("region", { name: "Chat" })).toHaveAttribute("aria-busy", "false");
    expect(within(run).getByRole("button", { name: "Stop" })).toBeInTheDocument();
  });

  it("shows the run working while a turn carries it on", async () => {
    const chat = idleRun();
    mount(chat, ["v1"]);
    const run = await screen.findByRole("region", { name: "Auto run" }, { timeout: 6000 });
    say(chat, { kind: "user", text: "carry on", selection: null });
    await waitFor(() => {
      expect(run.querySelector("[data-loading]")).not.toBeNull();
    });
    expect(run).not.toHaveTextContent(/Nothing is working/);
    expect(run).not.toHaveTextContent(/\ds/);
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

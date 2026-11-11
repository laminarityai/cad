import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { Refused, type Api } from "@/api/client";
import type { ConfirmationCard } from "@/api/types";
import { FakeChat, FakeViewer, fakeApi, setOf } from "@/test/fakes";
import { brief } from "@/test/fixtures";
import { materialLabel } from "./bits";
import { activityText, ChatPane, Composer, driverText } from "./Chat";
import { ConfirmCard, formOf } from "./Confirm";
import { Download } from "./Download";
import { Explorer } from "./Explorer";
import { loadWorkspace, type Brief } from "./model";
import { Start, Workspace } from "./Workspace";

const card = (items: number): ConfirmationCard & { snapshot: string } => ({
  snapshot: "s1",
  items: Array.from({ length: items }, (_, at) => ({
    kind: "requirements" as const,
    brief_id: `b${String(at + 1)}`,
    brief_text: "a hook",
    title: "What I will check",
    rows: [{ headline: "Mass at most 150 g", quote: "light", editable: { row: "r1", placeholder: "150 g" } }],
  })),
});

function wrap(api: Api, chat = new FakeChat()) {
  return ({ children }: { children: ReactNode }) => (
    <ServicesProvider services={{ api, viewer: new FakeViewer(), chat }}>{children}</ServicesProvider>
  );
}

describe("loadWorkspace", () => {
  it("reads each slot's option and material by name, the brief's confirmed fits, and what waits on the person", async () => {
    const set = setOf(["v1", "v2"]);
    const [first, second] = set.members;
    if (!first || !second) throw new Error("two members");
    first.material = { key: "prusament-pla", set_by: { kind: "agent_argument", statement: "The agent chose this material.", reason: "light" } };
    first.material_name = "Prusament PLA";
    first.option = { label: "Rounded corners", differs: "3 mm fillets on every edge" };
    const api = fakeApi([], {
      project: vi.fn(() =>
        Promise.resolve({
          project_id: "p1",
          briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }],
          context_parts: [
            { part_id: "k1", name: "rail", brief_id: "b1", variant_id: "v9", outcome: "confirmed" as const, size_mm: [30, 20, 10] as [number, number, number] },
            { part_id: "k2", name: "shelf", brief_id: "b1", variant_id: "v8", outcome: "waiting" as const, size_mm: [1, 2, 3] as [number, number, number] },
          ],
        }),
      ),
      variantSet: vi.fn(() => Promise.resolve(set)),
      confirmation: vi.fn(() => Promise.resolve(card(1))),
    });
    const model = await loadWorkspace(api, "p1");
    const [one] = model.briefs;
    expect(one?.state).toBe("waiting");
    expect(one?.title).toBe("Bracket");
    expect(one?.slots.map((slot) => slot.label)).toEqual(["Rounded corners", "Option 2"]);
    expect(one?.slots[0]?.differs).toBe("3 mm fillets on every edge");
    expect(one?.materialOf[1] && materialLabel(one.materialOf[1])).toBe("Prusament PLA · chosen by the agent");
    expect(one?.materialOf[2]).toBeNull();
    expect(one?.fits).toEqual([{ name: "rail", variantId: "v9" }]);
    expect(model.parts[0]).toEqual({ name: "rail", size: "30 × 20 × 10 mm", state: "confirmed" });
    expect(model.conversationId).toBe("c1");
  });

  it("names a brief with no options yet as building, and reads its options before anything is confirmed", async () => {
    const variantSet = vi.fn(() => Promise.resolve(setOf([])));
    const api = fakeApi([], {
      project: vi.fn(() =>
        Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: null }], context_parts: [] }),
      ),
      brief: vi.fn(() => Promise.resolve(brief(false))),
      variantSet,
    });
    const model = await loadWorkspace(api, "p1");
    expect(model.briefs[0]?.state).toBe("building");
    expect(model.briefs[0]?.title).toBe("Part 1");
    expect(model.confirmation).toBeNull();
    expect(variantSet).toHaveBeenCalledWith("p1", "b1");
  });
});

describe("the confirm card", () => {
  it("sends a per-item decline only when there is more than one item, and no edits on a declined one", () => {
    const edits = { "0-r1": "120", "1-r1": "90" };
    const several = formOf(card(2), "confirm", new Set([1]), edits, "too heavy");
    expect(Object.fromEntries(several)).toEqual({ snapshot: "s1", answer: "confirm", note: "too heavy", "edit-0-r1": "120", "decline-1": "decline" });
    const single = formOf(card(1), "decline", new Set(), edits, "no");
    expect(Object.fromEntries(single)).toEqual({ snapshot: "s1", answer: "decline", note: "no" });
  });

  it("posts the answer and shows the server's words when it refuses", async () => {
    const answer = vi.fn().mockResolvedValueOnce({ status: 400, text: "That is not a number." }).mockResolvedValueOnce({ status: 200, text: "" });
    const onAnswered = vi.fn();
    render(<ConfirmCard projectId="p1" card={card(1)} onAnswered={onAnswered} />, { wrapper: wrap(fakeApi([], { answer })) });
    expect(screen.getByRole("region", { name: "Confirm your targets" })).toBeInTheDocument();
    expect(screen.getByText("Only you can confirm.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("That is not a number.");
    expect(onAnswered).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(onAnswered).toHaveBeenCalledWith(true);
    });
    expect(answer).toHaveBeenCalledWith("p1", expect.any(URLSearchParams));
  });
});

describe("the chat", () => {
  it("names tools in plain words and an unknown tool as worked", () => {
    expect(activityText(["build_variant", "build_variant", "score_variant", "list_materials"])).toBe("Built 2, checked, worked");
  });

  it("says inline that the agent is still answering when a send is refused", async () => {
    const onSend = vi.fn(() => Promise.reject(new Refused(409, "busy")));
    render(<Composer placeholder="Ask" onSend={onSend} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "make it longer{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("still answering");
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("make it longer");
  });

  it("starts a chat with no project and opens the project its first brief makes", async () => {
    const chat = new FakeChat();
    chat.onSend = () => {
      chat.say({ kind: "tool_call", call_id: "t1", name: "create_brief", input: {} });
      chat.say({ kind: "tool_result", call_id: "t1", text: "", is_error: false });
    };
    render(
      <MemoryRouter initialEntries={["/new"]}>
        <Routes>
          <Route path="/new" element={<Start />} />
          <Route path="/projects/:projectId" element={<p>project page</p>} />
        </Routes>
      </MemoryRouter>,
      { wrapper: wrap(fakeApi([]), chat) },
    );
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "a hook{Enter}");
    expect(await screen.findByText("project page")).toBeInTheDocument();
    expect(chat.create).toHaveBeenCalledWith();
    expect(chat.sent).toEqual(["a hook"]);
  });
});

describe("the chat's driver line", () => {
  it("shows what the person did and never the prompt the model was given", () => {
    const prompt = "The person answered the confirmation page of project p-1: they confirmed 1 and declined 0. Call ask_to_confirm again.";
    expect(driverText(prompt)).toBe("You confirmed 1");
    expect(driverText(prompt.replace("1 and declined 0", "2 and declined 1"))).toBe("You confirmed 2, declined 1");
    expect(driverText("Call ask_to_confirm with the project.")).toBeNull();
    render(<ChatPane lines={[{ kind: "driver", seq: 1, text: prompt }]} running={false} card={null} composer={null} />);
    expect(screen.getByText("You confirmed 1")).toBeInTheDocument();
    expect(screen.queryByText(/ask_to_confirm/)).toBeNull();
  });

  it("tells a driver when the agent's turn is running", () => {
    const { rerender } = render(<ChatPane lines={[]} running card={null} composer={null} />);
    expect(screen.getByRole("region", { name: "Chat" })).toHaveAttribute("aria-busy", "true");
    rerender(<ChatPane lines={[]} running={false} card={null} composer={null} />);
    expect(screen.getByRole("region", { name: "Chat" })).toHaveAttribute("aria-busy", "false");
  });
});

const slot = (n: number) => ({ slot: n, label: `Option ${String(n)}`, differs: "", revisions: [{ n: 1, variantId: `v${String(n)}`, at: "2026-11-10T00:00:00Z" }] });
const part = (id: string, title: string, state: Brief["state"], slots: number[]): Brief => ({
  id,
  words: `words of ${title}`,
  title,
  state,
  slots: slots.map(slot),
  materialOf: {},
  fits: [],
});

describe("the explorer", () => {
  const props = (dispatch = vi.fn(), onNew = vi.fn()) => ({
    briefs: [part("b1", "Hook", "ready", [1, 2]), part("b2", "Lid", "waiting", [])],
    current: "b1",
    slot: 1,
    cards: {},
    parts: [{ name: "rail", size: "30 × 20 × 10 mm", state: "confirmed" as const }],
    sources: [
      { url: "https://www.example.com/pla", title: "PLA datasheet", page: "p. 2", retrieved: "2026-11-10", standard: null, quote: "q" },
      { url: "https://example.com/pla-2", title: "PLA datasheet: Mechanical", page: "p. 3", retrieved: "2026-11-10", standard: null, quote: "q" },
      { url: "https://example.org/petg", title: "", page: "", retrieved: "2026-11-10", standard: null, quote: "q" },
    ],
    dispatch,
    onNew,
  });

  it("selects a part and an option the way the stage tabs do", async () => {
    const dispatch = vi.fn();
    const { container } = render(<Explorer {...props(dispatch)} />);
    expect(container.querySelector("[data-tree]")).not.toBeNull();
    await userEvent.click(container.querySelector("[data-brief=b2]") as HTMLElement);
    expect(dispatch).toHaveBeenLastCalledWith({ type: "brief", briefId: "b2" });
    await userEvent.click(container.querySelector("[data-slot-node='2']") as HTMLElement);
    expect(dispatch).toHaveBeenCalledWith({ type: "brief", briefId: "b1" });
    expect(dispatch).toHaveBeenLastCalledWith({ type: "slot", briefId: "b1", slot: 2 });
    expect(container.querySelector("[data-slot-node='1']")).toHaveAttribute("aria-current", "true");
    expect(container.querySelector("[data-brief=b1]")).toHaveAttribute("aria-current", "true");
  });

  it("marks a part that waits on the person", () => {
    const { container } = render(<Explorer {...props()} />);
    expect(container.querySelector("[data-brief=b2] [data-brief-waiting]")).not.toBeNull();
    expect(container.querySelector("[data-brief=b1] [data-brief-waiting]")).toBeNull();
  });

  it("lists the context parts and the cited sources by document under Files, and folders collapse", async () => {
    const { container } = render(<Explorer {...props()} />);
    expect(container.querySelectorAll("[data-file]")).toHaveLength(1);
    expect(container.querySelectorAll("[data-source-folder]")).toHaveLength(2);
    await userEvent.click(screen.getByRole("button", { name: /^PLA datasheet/ }));
    expect(container.querySelectorAll("[data-file=source]")).toHaveLength(2);
    expect(screen.getByRole("link", { name: "p. 2" })).toHaveAttribute("href", "https://www.example.com/pla");
    expect(screen.getByRole("link", { name: "Mechanical, p. 3" })).toHaveAttribute("href", "https://example.com/pla-2");
    await userEvent.click(screen.getByRole("button", { name: /^example\.org/ }));
    expect(screen.getByRole("link", { name: "example.org" })).toHaveAttribute("href", "https://example.org/petg");
    await userEvent.click(screen.getByRole("button", { name: "Files" }));
    expect(screen.getByRole("button", { name: "Files" })).toHaveAttribute("aria-expanded", "false");
    expect(container.querySelectorAll("[data-file], [data-source-folder]")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Hook options" }));
    expect(container.querySelector("[data-slot-node]")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Hook options" }));
    expect(container.querySelectorAll("[data-slot-node]")).toHaveLength(2);
  });

  it("starts a new part, and offers no upload yet", async () => {
    const onNew = vi.fn();
    render(<Explorer {...props(vi.fn(), onNew)} />);
    await userEvent.click(screen.getByRole("button", { name: "New part" }));
    expect(onNew).toHaveBeenCalledTimes(1);
    const add = screen.getByRole("button", { name: "Add files" });
    expect(add).toBeDisabled();
    expect(add).toHaveAttribute("title", "Coming soon");
  });
});

describe("the download menu", () => {
  const saved: { href: string | null; download: string }[] = [];

  function savesLinks() {
    saved.length = 0;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      saved.push({ href: this.getAttribute("href"), download: this.download });
    });
  }

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const pick = async (label: "STEP" | "STL" | "3MF") => {
    await userEvent.click(screen.getByRole("button", { name: /Download/ }));
    await userEvent.click(await screen.findByRole("menuitem", { name: new RegExp(`^${label}`) }));
  };

  it("offers STEP, STL and 3MF", async () => {
    render(<Download variantId="v1" briefId="b1" />, { wrapper: wrap(fakeApi(["v1"])) });
    await userEvent.click(screen.getByRole("button", { name: /Download/ }));
    const items = await screen.findAllByRole("menuitem");
    expect(items.map((one) => one.querySelector("b")?.textContent)).toEqual(["STEP", "STL", "3MF"]);
  });

  it("says Preparing while the server makes the files, then saves the file under the server's name", async () => {
    savesLinks();
    const url = "/v1/exports/0123456789ab/" + "b".repeat(64) + ".stl?name=desk-box-option-1-rev2";
    const exportOf = vi
      .fn<Api["exportOf"]>()
      .mockResolvedValueOnce({ kind: "pending" })
      .mockResolvedValueOnce({ kind: "pending" })
      .mockResolvedValueOnce({ kind: "ready", url, filename: "desk-box-option-1-rev2.stl" });
    render(<Download variantId="v1" briefId="b1" />, { wrapper: wrap(fakeApi(["v1"], { exportOf })) });
    await pick("STL");
    const button = screen.getByRole("button", { name: "Preparing…" });
    expect(button).toBeDisabled();
    expect(saved).toEqual([]);
    expect(await screen.findByRole("button", { name: "Download" }, { timeout: 3000 })).toBeEnabled();
    expect(saved).toEqual([{ href: url, download: "desk-box-option-1-rev2.stl" }]);
    expect(exportOf).toHaveBeenCalledTimes(3);
    expect(exportOf).toHaveBeenLastCalledWith("v1", "b1", "stl");
  });

  it("says why when the server cannot make the file, and offers the menu again", async () => {
    savesLinks();
    const exportOf = vi.fn<Api["exportOf"]>().mockResolvedValue({ kind: "failed", reason: "the files are over 64 MiB" });
    render(<Download variantId="v1" briefId="b1" />, { wrapper: wrap(fakeApi(["v1"], { exportOf })) });
    await pick("3MF");
    expect(await screen.findByRole("alert")).toHaveTextContent("the files are over 64 MiB");
    expect(screen.getByRole("button", { name: "Download" })).toBeEnabled();
    expect(saved).toEqual([]);
  });

  it("says what the server refused with when the ask itself fails", async () => {
    savesLinks();
    const exportOf = vi.fn<Api["exportOf"]>().mockRejectedValue(new Refused(400, "variant v1 was not built"));
    render(<Download variantId="v1" briefId="b1" />, { wrapper: wrap(fakeApi(["v1"], { exportOf })) });
    await pick("STEP");
    expect(await screen.findByRole("alert")).toHaveTextContent("variant v1 was not built");
  });

  it("downloads the revision on the stage, not the newest", async () => {
    savesLinks();
    const set = setOf(["v1"]);
    const [member] = set.members;
    if (!member) throw new Error("one member");
    member.revision = 2;
    member.revisions = [
      { revision: 1, variant_id: "v1", code_sha256: "e".repeat(64), joined_at: "2026-11-10T00:00:00Z" },
      { revision: 2, variant_id: "v1b", code_sha256: "f".repeat(64), joined_at: "2026-11-10T01:00:00Z" },
    ];
    const exportOf = vi.fn<Api["exportOf"]>().mockResolvedValue({ kind: "ready", url: "/v1/exports/x", filename: "x.step" });
    const api = fakeApi(["v1"], {
      project: vi.fn(() =>
        Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [] }),
      ),
      variantSet: vi.fn(() => Promise.resolve(set)),
      exportOf,
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
    await userEvent.click(await screen.findByRole("button", { name: /Download/ }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /^STEP/ }));
    await waitFor(() => {
      expect(saved).toHaveLength(1);
    });
    expect(exportOf).toHaveBeenLastCalledWith("v1b", "b1", "step");
    await userEvent.click(screen.getByRole("button", { name: "Earlier revision" }));
    await userEvent.click(await screen.findByRole("button", { name: /Download/ }));
    await userEvent.click(await screen.findByRole("menuitem", { name: /^STL/ }));
    await waitFor(() => {
      expect(saved).toHaveLength(2);
    });
    expect(exportOf).toHaveBeenLastCalledWith("v1", "b1", "stl");
    expect(within(screen.getByRole("region", { name: "Chat" })).queryByRole("button", { name: /Download/ })).toBeNull();
  });
});

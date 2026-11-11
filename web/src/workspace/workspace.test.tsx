import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { Refused, type Api } from "@/api/client";
import type { ConfirmationCard } from "@/api/types";
import { FakeChat, FakeEvents, FakeViewer, fakeApi, setOf } from "@/test/fakes";
import { brief } from "@/test/fixtures";
import { materialLabel } from "./bits";
import { activityText, Composer } from "./Chat";
import { ConfirmCard, formOf } from "./Confirm";
import { loadWorkspace } from "./model";
import { Start } from "./Workspace";

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
    <ServicesProvider services={{ api, events: new FakeEvents(), viewer: new FakeViewer(), chat }}>{children}</ServicesProvider>
  );
}

describe("loadWorkspace", () => {
  it("reads each slot's material by name, the brief's confirmed fits, and what waits on the person", async () => {
    const set = setOf(["v1", "v2"]);
    const [first, second] = set.members;
    if (!first || !second) throw new Error("two members");
    first.material = { key: "prusament-pla", set_by: { kind: "agent_argument", statement: "The agent chose this material.", reason: "light" } };
    first.material_name = "Prusament PLA";
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
    expect(one?.slots.map((slot) => slot.label)).toEqual(["Option 1", "Option 2"]);
    expect(one?.materialOf[1] && materialLabel(one.materialOf[1])).toBe("Prusament PLA · chosen by the agent");
    expect(one?.materialOf[2]).toBeNull();
    expect(one?.fits).toEqual([{ name: "rail", variantId: "v9" }]);
    expect(model.parts[0]).toEqual({ name: "rail", size: "30 × 20 × 10 mm", state: "confirmed" });
    expect(model.conversationId).toBe("c1");
  });

  it("names a brief with no confirmed proposal as drafting and reads no options for it", async () => {
    const variantSet = vi.fn();
    const api = fakeApi([], {
      project: vi.fn(() =>
        Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: null }], context_parts: [] }),
      ),
      brief: vi.fn(() => Promise.resolve(brief(false))),
      variantSet,
    });
    const model = await loadWorkspace(api, "p1");
    expect(model.briefs[0]?.state).toBe("drafting");
    expect(model.confirmation).toBeNull();
    expect(variantSet).not.toHaveBeenCalled();
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

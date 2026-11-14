import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import type { Event } from "@/api/types";
import { ServicesProvider } from "@/app/context";
import { Workspace } from "@/features/workspace/Workspace";
import { FakeChat, FakeViewer, fakeApi } from "@/test/fakes";
import { DEFAULTS, REST, answerText, askedOf, type Question } from "./questions";
import { chatReducer, chatStart, type ChatState } from "./state";

const QUESTIONS: Question[] = [
  { question: "How wide is the pump's inlet?", default: "20 mm", why: "It sets the eye of the impeller.", suggestions: ["15 mm", "20 mm"] },
  { question: "What does it pump?", default: "clean water", why: "It sets the material.", suggestions: [] },
];

const asked = (id = "q"): Event[] => [
  { kind: "tool_call", call_id: id, name: "ask_questions", input: {} },
  { kind: "tool_result", call_id: id, text: JSON.stringify({ questions: QUESTIONS, next: "" }), is_error: false },
];

const play = (events: Event[]): ChatState => events.reduce((held, event, at) => chatReducer(held, { type: "event", seq: at + 1, event }), chatStart("c1"));

describe("askedOf", () => {
  it("finds the newest questions the person has not answered", () => {
    const lines = play([{ kind: "user", text: "an impeller", selection: null }, ...asked()]).lines;
    expect(askedOf(lines)?.questions).toEqual(QUESTIONS);
    expect(askedOf(play([...asked(), { kind: "user", text: "20 mm", selection: null }]).lines)).toBeNull();
  });

  it("shows nothing for questions that were refused", () => {
    const refused: Event[] = [
      { kind: "tool_call", call_id: "q", name: "ask_questions", input: {} },
      { kind: "tool_result", call_id: "q", text: "too many questions", is_error: true },
    ];
    expect(askedOf(play(refused).lines)).toBeNull();
  });
});

describe("answerText", () => {
  it("sends one line for each answer and the defaults for the rest", () => {
    expect(answerText(QUESTIONS, ["32 mm", ""])).toBe(`How wide is the pump's inlet?: 32 mm\n${REST}`);
    expect(answerText(QUESTIONS, ["32 mm", "sea water"])).toBe("How wide is the pump's inlet?: 32 mm\nWhat does it pump?: sea water");
    expect(answerText(QUESTIONS, [" ", ""])).toBe(DEFAULTS);
  });
});

describe("web search lines", () => {
  it("shows a search as a tool line with the pages it found", () => {
    const state = play([
      { kind: "web_search", call_id: "s", query: "pump impeller material", raw: {} },
      { kind: "web_search_result", call_id: "s", pages: [{ title: "Impellers", url: "https://example.com/a" }], error: null, raw: {} },
      { kind: "web_search", call_id: "t", query: "more", raw: {} },
      { kind: "web_search_result", call_id: "t", pages: [], error: "max_uses_exceeded", raw: {} },
    ]);
    expect(state.lines).toMatchObject([
      { kind: "tool", name: "web_search", input: { query: "pump impeller material" }, result: { text: "Impellers · https://example.com/a", isError: false } },
      { kind: "tool", name: "web_search", result: { text: "max_uses_exceeded", isError: true } },
    ]);
  });
});

function mount(chat: FakeChat) {
  const api = fakeApi(["v1"], {
    project: vi.fn(() => Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] })),
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

describe("the questions card", () => {
  it("asks one question at a time with its default, and sends the answers as a chat message", async () => {
    const chat = new FakeChat();
    mount(chat);
    for (const event of asked()) chat.say(event);
    chat.say({ kind: "turn_ended" });
    const user = userEvent.setup();
    expect(await screen.findByText("How wide is the pump's inlet?")).toBeTruthy();
    expect(screen.getByText("Default: 20 mm")).toBeTruthy();
    await user.type(screen.getByLabelText("Your answer"), "32 mm");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Default: clean water")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Send answers" }));
    await waitFor(() => {
      expect(chat.sent).toEqual([`How wide is the pump's inlet?: 32 mm\n${REST}`]);
    });
    expect(screen.queryByText("Default: clean water")).toBeNull();
  });

  it("fills the answer from a suggestion, and Skip asks for the defaults", async () => {
    const chat = new FakeChat();
    mount(chat);
    for (const event of asked()) chat.say(event);
    const user = userEvent.setup();
    await user.click(await screen.findByRole("button", { name: "15 mm" }));
    expect(screen.getByLabelText<HTMLInputElement>("Your answer").value).toBe("15 mm");
    await user.click(screen.getByRole("button", { name: "15 mm" }));
    await user.click(screen.getByRole("button", { name: "Skip" }));
    await waitFor(() => {
      expect(chat.sent).toEqual([DEFAULTS]);
    });
  });
});

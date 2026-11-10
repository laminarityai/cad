import { describe, expect, it } from "vitest";
import type { Event } from "@/api/types";
import { chatReducer, chatStart, type ChatAction, type ChatState } from "./state";

const play = (state: ChatState, events: Event[], from = 1): ChatState =>
  events.reduce((held, event, at) => chatReducer(held, { type: "event", seq: from + at, event } satisfies ChatAction), state);

const call = (id: string, name: string): Event => ({ kind: "tool_call", call_id: id, name, input: {} });
const result = (id: string, text: string, isError = false): Event => ({ kind: "tool_result", call_id: id, text, is_error: isError });

describe("chatReducer", () => {
  it("merges a tool result into its call and follows the turn from the user's message to its end", () => {
    let state = play(chatStart("c1"), [{ kind: "user", text: "make the wall 4 mm" }, call("a", "build_variant")]);
    expect(state.turn).toBe("running");
    state = play(state, [result("a", "{}"), { kind: "agent", text: "Done." }, { kind: "turn_ended" }], 3);
    expect(state.turn).toBe("idle");
    expect(state.lines.map((one) => one.kind)).toEqual(["user", "tool", "agent"]);
    expect(state.lines[1]).toMatchObject({ name: "build_variant", result: { text: "{}", isError: false } });
  });

  it("ignores an event it has seen, so a resumed stream adds nothing twice", () => {
    const once = play(chatStart("c1"), [{ kind: "agent", text: "hi" }]);
    expect(chatReducer(once, { type: "event", seq: 1, event: { kind: "agent", text: "hi" } })).toBe(once);
  });

});

import { describe, expect, it } from "vitest";
import { FrameReader } from "./sse";

describe("FrameReader", () => {
  it("joins a frame that arrives in pieces and skips the keepalive comment", () => {
    const reader = new FrameReader();
    expect(reader.push("id: 3\nevent: ag")).toEqual([]);
    expect(reader.push('ent\ndata: {"kind":"agent"}\n\n: keepalive\n\nid: 4\n')).toEqual([
      { id: "3", event: "agent", data: '{"kind":"agent"}' },
    ]);
    expect(reader.push('event: turn_ended\ndata: {"kind":"turn_ended"}\r\n\r\n')).toEqual([
      { id: "4", event: "turn_ended", data: '{"kind":"turn_ended"}' },
    ]);
  });
});

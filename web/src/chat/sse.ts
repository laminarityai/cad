export interface Frame {
  id: string | null;
  event: string;
  data: string;
}

/** Lines that start with `:` are server-sent event comments (the server's keepalive) and make no frame. */
export class FrameReader {
  private held = "";

  push(chunk: string): Frame[] {
    this.held += chunk.replace(/\r\n?/g, "\n");
    const parts = this.held.split("\n\n");
    this.held = parts.pop() ?? "";
    return parts.flatMap((part) => {
      const frame: Frame = { id: null, event: "message", data: "" };
      let any = false;
      for (const line of part.split("\n")) {
        if (line === "" || line.startsWith(":")) continue;
        const colon = line.indexOf(":");
        const field = colon < 0 ? line : line.slice(0, colon);
        const value = colon < 0 ? "" : line.slice(colon + 1).replace(/^ /, "");
        if (field === "id") frame.id = value;
        else if (field === "event") frame.event = value;
        else if (field === "data") frame.data = frame.data === "" ? value : `${frame.data}\n${value}`;
        else continue;
        any = true;
      }
      return any ? [frame] : [];
    });
  }
}

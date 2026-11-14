import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { ServicesProvider } from "@/app/context";
import { FakeChat, FakeViewer, fakeApi } from "@/test/fakes";
import { Start } from "./Workspace";

function start(chat: FakeChat) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ServicesProvider services={{ api: fakeApi([]), viewer: new FakeViewer(), chat }}>{children}</ServicesProvider>
  );
  render(
    <MemoryRouter initialEntries={["/new"]}>
      <Routes>
        <Route path="/new" element={<Start />} />
        <Route path="/projects/:projectId" element={<p>project page</p>} />
      </Routes>
    </MemoryRouter>,
    { wrapper },
  );
}

describe("a new project's first message", () => {
  it("starts a chat with no project and opens the project its first brief makes", async () => {
    const chat = new FakeChat();
    chat.onSend = () => {
      chat.say({ kind: "tool_call", call_id: "t1", name: "create_brief", input: {} });
      chat.say({ kind: "tool_result", call_id: "t1", text: "", is_error: false });
    };
    start(chat);
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "a hook{Enter}");
    expect(await screen.findByText("project page")).toBeInTheDocument();
    expect(chat.create).toHaveBeenCalledWith();
    expect(chat.sent).toEqual(["a hook"]);
  });

  it("keeps the first message and says why when its send fails, and sends it again in the same chat", async () => {
    const chat = new FakeChat();
    chat.send.mockImplementationOnce(() => Promise.reject(new Error("network down")));
    start(chat);
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "a hook{Enter}");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message" })).toHaveValue("a hook");
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "{Enter}");
    await waitFor(() => {
      expect(chat.sent).toEqual(["a hook"]);
    });
    expect(chat.create).toHaveBeenCalledTimes(1);
  });
});

import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { ServicesProvider } from "@/app/context";
import { SetPage } from "@/features/set/SetPage";
import { deflection, feaPending, mass, massResult, snapshot } from "@/test/fixtures";
import { FakeChat, FakeEvents, FakeViewer, fakeApi, setOf } from "@/test/fakes";
import type { VariantSetView } from "@/api/types";

const revised = (variant: string): VariantSetView => {
  const set = setOf([variant]);
  return { ...set, members: set.members.map((one) => ({ ...one, revision: 2 })) };
};

function Where() {
  return <p data-testid="where">{useLocation().search}</p>;
}

function mount(options: { entry?: string; chat?: FakeChat; reads?: () => VariantSetView } = {}) {
  const chat = options.chat ?? new FakeChat();
  const events = new FakeEvents();
  const reads = options.reads ?? (() => setOf(["v1"]));
  const api = fakeApi(["v1"], { variantSet: () => Promise.resolve(reads()) });
  render(
    <ServicesProvider services={{ api, events, viewer: new FakeViewer(), chat }}>
      <MemoryRouter initialEntries={[options.entry ?? "/projects/p1/briefs/b1"]}>
        <Where />
        <Routes>
          <Route path="projects/:projectId/briefs/:briefId" element={<SetPage />} />
        </Routes>
      </MemoryRouter>
    </ServicesProvider>,
  );
  return { chat, events, api };
}

describe("chat on the set page", () => {
  it("shows a change asked for in chat as the slot's next revision at once, with no reload", async () => {
    let built = false;
    let reads = 0;
    const chat = new FakeChat();
    chat.mode = "design";
    chat.onSend = () => {
      chat.say({ kind: "tool_call", call_id: "t1", name: "build_variant", input: { slot: 1 } });
      built = true;
      chat.say({ kind: "tool_result", call_id: "t1", text: "{}", is_error: false });
      chat.say({ kind: "agent", text: "Rebuilt slot 1." });
      chat.say({ kind: "turn_ended" });
    };
    const { events } = mount({ chat, reads: () => {
        reads += 1;
        return built ? revised("v1b") : setOf(["v1"]);
      },
    });
    await waitFor(() => {
      expect(events.opened.map((one) => one.query.variantId)).toEqual(["v1"]);
    });
    act(() => {
      events.push(snapshot("v1", [mass("pass"), deflection()], [massResult(), feaPending()]));
    });
    const readsBefore = reads;

    await userEvent.setup().type(screen.getByRole("textbox", { name: /message/i }), "make the wall 4 mm{Enter}");

    expect(chat.sent).toEqual(["make the wall 4 mm"]);
    await waitFor(() => {
      expect(events.opened.map((one) => [one.query.variantId, one.closed])).toEqual([
        ["v1", true],
        ["v1b", false],
      ]);
    });
    expect(screen.getByRole("region", { name: "Scorecard" })).toHaveTextContent("revision 2");
    expect(reads).toBeGreaterThan(readsBefore);
    expect(screen.getByText("Rebuilt slot 1.")).toBeInTheDocument();
    expect(screen.getByText(/^build_variant/)).toBeInTheDocument();
  });

  it("makes the conversation on the first message and puts its id in the address", async () => {
    const { chat } = mount();
    await userEvent.setup().type(await screen.findByRole("textbox", { name: /message/i }), "hi{Enter}");
    expect(chat.create).toHaveBeenCalledExactlyOnceWith("p1", "b1");
    expect(chat.send).toHaveBeenCalledWith("c_new", "hi");
    await waitFor(() => {
      expect(screen.getByTestId("where")).toHaveTextContent("?chat=c_new");
    });
    expect(await screen.findByText("hi")).toBeInTheDocument();
  });

  it("brings back the history of a conversation named in the address", async () => {
    const chat = new FakeChat();
    chat.say({ kind: "user", text: "earlier question" });
    chat.say({ kind: "agent", text: "earlier answer" });
    mount({ chat, entry: "/projects/p1/briefs/b1?chat=c_old" });
    expect(await screen.findByText("earlier answer")).toBeInTheDocument();
    expect(chat.followed).toEqual(["c_old"]);
    expect(chat.create).not.toHaveBeenCalled();
  });

  it("shows a refused tool in the chat, as the server said it", async () => {
    const chat = new FakeChat();
    chat.say({ kind: "tool_call", call_id: "t1", name: "build_variant", input: {} });
    chat.say({ kind: "tool_result", call_id: "t1", text: "build_variant is refused in Plan mode", is_error: true });
    mount({ chat, entry: "/projects/p1/briefs/b1?chat=c_old" });
    expect((await screen.findAllByText(/refused in Plan mode/)).length).toBeGreaterThan(0);
  });

  it("closes its streams while the tab is hidden and, shown again, follows on from the last event", async () => {
    const shown = (visibility: DocumentVisibilityState) => {
      Object.defineProperty(document, "visibilityState", { value: visibility, configurable: true });
      act(() => {
        document.dispatchEvent(new Event("visibilitychange"));
      });
    };
    try {
      const chat = new FakeChat();
      chat.say({ kind: "agent", text: "Built slot 1." });
      const { events } = mount({ chat, entry: "/projects/p1/briefs/b1?chat=c_old" });
      await screen.findByText("Built slot 1.");
      await waitFor(() => {
        expect(events.opened.filter((one) => !one.closed)).toHaveLength(1);
      });
      shown("hidden");
      expect(events.opened.filter((one) => !one.closed)).toHaveLength(0);
      chat.say({ kind: "agent", text: "Scored it." });
      expect(screen.queryByText("Scored it.")).not.toBeInTheDocument();
      shown("visible");
      expect(await screen.findByText("Scored it.")).toBeInTheDocument();
      expect(screen.getAllByText("Built slot 1.")).toHaveLength(1);
      expect(events.opened.filter((one) => !one.closed)).toHaveLength(1);
    } finally {
      shown("visible");
    }
  });

  it("says the conversation is not in the account and shows no message", async () => {
    const chat = new FakeChat();
    chat.follow = (_id, _after, handlers) => {
      handlers.onLink("not_found");
      return () => undefined;
    };
    mount({ chat, entry: "/projects/p1/briefs/b1?chat=c_alice" });
    expect(await screen.findByText(/not in your account/i)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message/i })).not.toBeInTheDocument();
  });
});

import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { Refused, SignedOut } from "@/api/client";
import { deflection, deflectionDone, feaPending, mass, massResult, snapshot } from "@/test/fixtures";
import { FakeChat, FakeEvents, FakeViewer, fakeApi, setOf } from "@/test/fakes";
import { FOLLOW_MS, SetPage } from "./SetPage";

function mountSet(api = fakeApi(["v1", "v2"]), chat = new FakeChat()) {
  const events = new FakeEvents();
  const viewer = new FakeViewer();
  const view = render(
    <ServicesProvider services={{ api, events, viewer, chat }}>
      <MemoryRouter initialEntries={["/projects/p1/briefs/b1"]}>
        <Routes>
          <Route path="projects/:projectId/briefs/:briefId" element={<SetPage />} />
        </Routes>
      </MemoryRouter>
    </ServicesProvider>,
  );
  return { events, viewer, api, chat, view };
}

const pending = () => snapshot("v1", [mass("pass"), deflection()], [massResult(), feaPending()]);
const done = () =>
  snapshot("v1", [mass("pass"), deflectionDone()], [massResult()], "after");

describe("SetPage", () => {
  it("opens one stream and one viewer per member", async () => {
    const { events, viewer } = mountSet();
    await waitFor(() => {
      expect(events.opened.map((one) => one.query.variantId)).toEqual(["v1", "v2"]);
    });
    expect(events.opened[0]?.query).toMatchObject({ materialKey: "prusament-pla", briefId: "b1" });
    await waitFor(() => {
      expect(viewer.mounted).toHaveLength(2);
    });
  });

  it("draws a pending row without a verdict, then replaces it in place when the next snapshot arrives", async () => {
    const { events } = mountSet(fakeApi(["v1"]));
    await waitFor(() => {
      expect(events.opened).toHaveLength(1);
    });
    act(() => {
      events.push(pending());
    });
    const card = await screen.findByRole("region", { name: "Scorecard" });
    const row = card.querySelector("[data-key='req:r2']");
    expect(row).toHaveAttribute("data-row", "pending");
    expect(within(row as HTMLElement).getByText("pending")).toBeInTheDocument();
    const tones = [...(row as HTMLElement).querySelectorAll("[data-tone]")].map((one) => one.getAttribute("data-tone"));
    expect(tones).toEqual(["pending"]);

    act(() => {
      events.push(done());
    });
    await waitFor(() => {
      expect(card.querySelector("[data-key='req:r2']")).toHaveAttribute("data-row", "settled");
    });
  });

  it("closes every stream and viewer when the page unmounts", async () => {
    const { events, viewer, view } = mountSet();
    await waitFor(() => {
      expect(viewer.mounted).toHaveLength(2);
    });
    view.unmount();
    expect(events.opened.every((one) => one.closed)).toBe(true);
    await waitFor(() => {
      expect(viewer.stopped).toBe(2);
    });
  });

  it("says it is signed out and links to the sign-in page when the server says 401", async () => {
    const api = fakeApi([], {
      variantSet: () => Promise.reject(new SignedOut()),
    });
    mountSet(api);
    const link = await screen.findByRole("link", { name: /sign in/i });
    expect(link).toHaveAttribute("href", expect.stringContaining("/confirm"));
  });

  it("expands a truncated note on click", async () => {
    const { events } = mountSet(fakeApi(["v1"]));
    await waitFor(() => {
      expect(events.opened).toHaveLength(1);
    });
    act(() => {
      events.push(pending());
    });
    const note = await screen.findAllByRole("button", { name: /mass check measured/i });
    expect(note[0]).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(note[0] as HTMLElement);
    expect(note[0]).toHaveAttribute("aria-expanded", "true");
  });

  it("says the material is the table's first when the brief confirms none", async () => {
    mountSet(fakeApi(["v1"]));
    expect(await screen.findByText(/confirms no material/i)).toBeInTheDocument();
  });

  describe("following the set", () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    it("moves a rebuilt slot to its new variant without a reload, and keeps the page through a failed read", async () => {
      vi.useFakeTimers({ shouldAdvanceTime: true });
      const rebuilt = setOf(["v1b"]);
      const reads = [setOf(["v1"]), null, { ...rebuilt, members: rebuilt.members.map((one) => ({ ...one, revision: 2 })) }];
      let at = 0;
      const api = fakeApi(["v1"], {
        variantSet: vi.fn(() => {
          const read = reads[Math.min(at++, reads.length - 1)];
          return read ? Promise.resolve(read) : Promise.reject(new Refused(503, "restarting"));
        }),
      });
      const { events, viewer } = mountSet(api);
      await waitFor(() => {
        expect(events.opened.map((one) => one.query.variantId)).toEqual(["v1"]);
      });
      act(() => {
        events.push(snapshot("v1", [mass("pass")], [massResult()]));
      });
      await act(() => vi.advanceTimersByTimeAsync(FOLLOW_MS));
      expect(screen.getByRole("region", { name: "Scorecard" })).toBeInTheDocument();
      await act(() => vi.advanceTimersByTimeAsync(FOLLOW_MS));
      await waitFor(() => {
        expect(events.opened.map((one) => [one.query.variantId, one.closed])).toEqual([
          ["v1", true],
          ["v1b", false],
        ]);
      });
      const card = screen.getByRole("region", { name: "Scorecard" });
      expect(card).toHaveTextContent("revision 2");
      expect(card.querySelector("[data-key='req:r1']")).toHaveAttribute("data-row", "pending");
      expect(card.querySelector("[data-ghost]")).toHaveTextContent("before: mass 41.2 g ≤ 50 g");
      await waitFor(() => {
        expect(viewer.mounted).toHaveLength(2);
      });
    });
  });
});

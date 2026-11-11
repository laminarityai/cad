import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { Refused } from "@/api/client";
import { FakeChat, FakeViewer, fakeApi, setOf } from "@/test/fakes";
import { Workspace } from "./Workspace";

const HINT = "Click a face or edge to point at it. Shift-click adds, double-click picks the whole part.";

function twoRevisions() {
  const set = setOf(["v1"]);
  const [member] = set.members;
  if (!member) throw new Error("one member");
  member.revision = 2;
  member.revisions = [
    { revision: 1, variant_id: "v1", code_sha256: "e".repeat(64), joined_at: "2026-11-10T00:00:00Z" },
    { revision: 2, variant_id: "v1b", code_sha256: "f".repeat(64), joined_at: "2026-11-10T01:00:00Z" },
  ];
  return set;
}

async function open(chat = new FakeChat(), viewer = new FakeViewer()) {
  const api = fakeApi(["v1"], {
    project: vi.fn(() =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [] }),
    ),
    variantSet: vi.fn(() => Promise.resolve(twoRevisions())),
  });
  const { container } = render(
    <ServicesProvider services={{ api, viewer, chat }}>
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <Routes>
          <Route path="projects/:projectId" element={<Workspace />} />
        </Routes>
      </MemoryRouter>
    </ServicesProvider>,
  );
  await waitFor(() => {
    expect(viewer.selected.length).toBeGreaterThan(0);
  });
  const picks = () => container.querySelector("[data-picks]")?.getAttribute("data-picks");
  const hint = () => container.querySelector("[data-pick-hint]")?.textContent;
  const chip = () => container.querySelector("[data-selection-chip]");
  return { chat, viewer, container, picks, hint, chip };
}

describe("pointing at a design", () => {
  it("highlights a click, adds with shift, and offers no disabled Point at it button", async () => {
    const { viewer, picks, hint, chip } = await open();
    expect(screen.queryByRole("button", { name: /Point at it/ })).toBeNull();
    expect(hint()).toBe(HINT);
    expect(picks()).toBe("0");
    viewer.pick({ kind: "face", index: 3 });
    expect(viewer.highlighted).toEqual([{ kind: "face", index: 3 }]);
    expect(picks()).toBe("1");
    expect(hint()).toBe("1 face selected · Esc clears");
    expect(chip()).toHaveTextContent("1 face");
    viewer.pick({ kind: "edge", index: 8 }, true);
    expect(chip()).toHaveTextContent("1 face, 1 edge");
    viewer.pick({ kind: "face", index: 3 }, true);
    expect(chip()).toHaveTextContent("1 edge");
    viewer.pick({ kind: "part" });
    expect(chip()).toHaveTextContent("Whole part");
    expect(viewer.highlighted).toEqual([{ kind: "part" }]);
  });

  it("clears on empty space, on Escape and from the chip's remove button", async () => {
    const { viewer, picks, hint, chip } = await open();
    viewer.pick({ kind: "face", index: 1 });
    viewer.pick(null);
    expect(chip()).toBeNull();
    expect(viewer.highlighted).toEqual([]);
    viewer.pick({ kind: "face", index: 1 });
    await userEvent.keyboard("{Escape}");
    expect(picks()).toBe("0");
    expect(hint()).toBe(HINT);
    viewer.pick({ kind: "face", index: 1 });
    await userEvent.click(screen.getByRole("button", { name: "Remove selection" }));
    expect(chip()).toBeNull();
    expect(viewer.highlighted).toEqual([]);
  });

  it("asks for a change to the selection and sends it with the message, then clears it", async () => {
    const { chat, viewer, chip, container } = await open();
    const box = screen.getByRole("textbox", { name: "Message" });
    viewer.pick({ kind: "face", index: 4 });
    viewer.pick({ kind: "face", index: 6 }, true);
    expect(box).toHaveAttribute("placeholder", "Ask for a change to the selection, such as: make this thicker");
    await userEvent.type(box, "make this thicker{Enter}");
    await waitFor(() => {
      expect(chip()).toBeNull();
    });
    expect(chat.sent).toEqual(["make this thicker"]);
    expect(chat.picked).toEqual([{ variant_id: "v1b", faces: [4, 6], edges: [], part: false }]);
    expect(await screen.findByText("Pointed at 2 faces", { exact: false })).toBeInTheDocument();
    expect(container.querySelector("[data-said-selection]")).toHaveTextContent("Pointed at 2 faces");
    expect(screen.getByRole("textbox", { name: "Message" }).getAttribute("placeholder")).not.toContain("the selection");
  });

  it("sends a plain message with no selection and shows no chip under it", async () => {
    const { chat, container } = await open();
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "hello{Enter}");
    await waitFor(() => {
      expect(chat.sent).toEqual(["hello"]);
    });
    expect(chat.picked).toEqual([undefined]);
    expect(container.querySelector("[data-said-selection]")).toBeNull();
  });

  it("shows the server's refusal and keeps the selection so the person can try again", async () => {
    const { chat, viewer, chip } = await open();
    chat.send.mockRejectedValueOnce(new Refused(422, "That face is not on this revision."));
    viewer.pick({ kind: "face", index: 4 });
    await userEvent.type(screen.getByRole("textbox", { name: "Message" }), "round it{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("That face is not on this revision.");
    expect(chip()).toHaveTextContent("1 face");
  });

  it("drops the selection when another revision comes on screen", async () => {
    const { viewer, picks, hint, chip } = await open();
    viewer.pick({ kind: "face", index: 2 });
    expect(chip()).not.toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Earlier revision" }));
    await waitFor(() => {
      expect(picks()).toBe("0");
    });
    expect(chip()).toBeNull();
    expect(hint()).toBe(HINT);
    expect(viewer.highlighted).toEqual([]);
    viewer.pick({ kind: "edge", index: 1 });
    expect(chip()).toHaveTextContent("1 edge");
    await userEvent.click(screen.getByRole("button", { name: "Later revision" }));
    await waitFor(() => {
      expect(chip()).toBeNull();
    });
  });
});

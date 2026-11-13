import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import type { Api } from "@/api/client";
import { FakeChat, FakeViewer, fakeApi } from "@/test/fakes";
import { Files } from "./Files";
import type { Doc, Part } from "./model";

const motor: Part = { id: "part-0123456789abcdef", name: "motor", size: "42 × 42 × 40 mm · 4 holes", state: "confirmed", uploaded: true, leftOut: "1 of 3 bodies could not be read" };

function calls() {
  const addFile = vi.fn((_projectId: string, file: File) =>
    Promise.resolve({ kind: "document" as const, part: null, document: { file_id: "file-0123456789abcdef", name: file.name, media_type: "application/pdf" as const, size: file.size, withheld: false } }),
  );
  const declinePart = vi.fn((_projectId: string, partId: string) => Promise.resolve({ part_id: partId, declined: true }));
  return { api: fakeApi([], { addFile, declinePart }), addFile, declinePart };
}

function shown(api: Api, parts: Part[] = [], documents: Doc[] = []) {
  const onChanged = vi.fn();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ServicesProvider services={{ api, viewer: new FakeViewer(), chat: new FakeChat() }}>
      <ul>{children}</ul>
    </ServicesProvider>
  );
  const view = render(<Files projectId="p1" parts={parts} documents={documents} sources={[]} open toggle={vi.fn()} onChanged={onChanged} />, { wrapper });
  return { ...view, onChanged };
}

describe("adding files", () => {
  it("asks whether a PDF is a licensed standard, sends nothing until the person answers, and reads it by default", async () => {
    const { api, addFile } = calls();
    const { onChanged } = shown(api);
    const pdf = new File(["%PDF-1.7"], "spec.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText("Choose files"), pdf);
    expect(screen.getByRole("group", { name: "Is spec.pdf a licensed standard?" })).toBeInTheDocument();
    expect(addFile).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "No, the agent may read it" }));
    await waitFor(() => {
      expect(onChanged).toHaveBeenCalledTimes(1);
    });
    expect(addFile).toHaveBeenCalledWith("p1", pdf, null, false);
  });

  it("keeps a PDF the person calls a standard from the agent", async () => {
    const { api, addFile } = calls();
    shown(api);
    const pdf = new File(["%PDF-1.7"], "din.pdf", { type: "application/pdf" });
    await userEvent.upload(screen.getByLabelText("Choose files"), pdf);
    await userEvent.click(screen.getByRole("button", { name: "Yes, keep it from the agent" }));
    await waitFor(() => {
      expect(addFile).toHaveBeenCalledWith("p1", pdf, null, true);
    });
  });

  it("marks a withheld file in the list", () => {
    const { api } = calls();
    shown(api, [], [{ id: "file-0123456789abcdef", name: "din.pdf", withheld: true }, { id: "file-fedcba9876543210", name: "spec.md", withheld: false }]);
    expect(screen.getByText("Standard, kept from the agent")).toBeInTheDocument();
    expect(screen.getAllByText(/kept from the agent/)).toHaveLength(1);
  });

  it("asks for the units of an STL, with no default, and sends nothing until the person picks", async () => {
    const { api, addFile } = calls();
    shown(api);
    const stl = new File(["solid"], "bracket.stl");
    await userEvent.upload(screen.getByLabelText("Choose files"), stl);
    expect(screen.getByRole("group", { name: "Units of bracket.stl" })).toBeInTheDocument();
    expect(addFile).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Inches" }));
    await waitFor(() => {
      expect(addFile).toHaveBeenCalledWith("p1", stl, "in", false);
    });
    expect(screen.queryByRole("group", { name: "Units of bracket.stl" })).toBeNull();
  });

  it("takes files dropped on the Files folder", async () => {
    const { api, addFile } = calls();
    const { container } = shown(api);
    const step = new File(["ISO-10303-21;"], "motor.step");
    fireEvent.drop(container.querySelector("[data-files-drop]") as HTMLElement, { dataTransfer: { files: [step] } });
    await waitFor(() => {
      expect(addFile).toHaveBeenCalledWith("p1", step, null, false);
    });
  });

  it("says why the server refused a file", async () => {
    const api = fakeApi([], { addFile: vi.fn(() => Promise.reject(new Error("no solid could be read from the file"))) });
    shown(api);
    await userEvent.upload(screen.getByLabelText("Choose files"), new File(["x"], "empty.step"));
    expect(await screen.findByRole("alert")).toHaveTextContent("empty.step: no solid could be read from the file");
  });

  it("shows a supplied part with what could not be read, and declines it from its row", async () => {
    const { api, declinePart } = calls();
    const { onChanged } = shown(api, [motor]);
    expect(screen.getByText("42 × 42 × 40 mm · 4 holes · supplied by you")).toBeInTheDocument();
    expect(screen.getByText("1 of 3 bodies could not be read")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Decline motor" }));
    await waitFor(() => {
      expect(onChanged).toHaveBeenCalledTimes(1);
    });
    expect(declinePart).toHaveBeenCalledWith("p1", motor.id);
  });
});

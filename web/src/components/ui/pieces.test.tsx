import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Markdown } from "@/features/workspace/Markdown";
import { chatReducer, chatStart, shownLines } from "@/features/chat/state";
import { CodeBlock } from "./code-block";
import { ContextCard } from "./context-card";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "./dropdown-menu";

describe("code block", () => {
  it("shows the fence's language and numbered lines, and copies the exact code", async () => {
    const write = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, "clipboard", { value: { writeText: write }, configurable: true });
    render(<Markdown text={"```python\nx = 1\n\ny = 2\n```"} />);
    expect(screen.getByText("python")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-line-number]")).toHaveLength(3);
    await userEvent.click(screen.getByRole("button", { name: "Copy code" }));
    expect(write).toHaveBeenCalledWith("x = 1\n\ny = 2");
    expect(await screen.findByText("Copied")).toBeInTheDocument();
  });

  it("names a fence with no language as code", () => {
    render(<CodeBlock code="a" />);
    expect(screen.getByText("code")).toBeInTheDocument();
  });
});

describe("context card", () => {
  it("shows the title, the quote and the page address as a link", () => {
    render(<ContextCard title="Table 2" quote="Yield strength 40 MPa" address="example.com" href="https://example.com/ds.pdf" />);
    expect(screen.getByText("Table 2")).toBeInTheDocument();
    expect(screen.getByText("Yield strength 40 MPa")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "example.com" })).toHaveAttribute("href", "https://example.com/ds.pdf");
  });
});

describe("dropdown menu", () => {
  it("keeps its items and glides one layer to the keyboard-highlighted item", async () => {
    render(
      <DropdownMenu>
        <DropdownMenuTrigger>Open</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem>First</DropdownMenuItem>
          <DropdownMenuItem>Second</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(await screen.findAllByRole("menuitem")).toHaveLength(2);
    const layer = document.querySelector("[data-glide-layer]");
    expect(layer).not.toBeNull();
    await userEvent.hover(screen.getByRole("menuitem", { name: "Second" }));
    await waitFor(() => {
      expect(layer).toHaveAttribute("data-shown");
    });
    await userEvent.unhover(screen.getByRole("menuitem", { name: "Second" }));
    await userEvent.keyboard("{Escape}");
  });
});

describe("streaming reply", () => {
  const sample = "Built **3** options, see `a`.";
  const text = (view: HTMLElement) => view.textContent;

  it("reads the same while streaming as when stored", () => {
    const stored = render(<Markdown text={sample} />);
    const streaming = render(<Markdown text={sample} streaming />);
    expect(text(streaming.container)).toBe(text(stored.container));
    expect(streaming.container.querySelector("[data-stream-caret]")).not.toBeNull();
    expect(stored.container.querySelector("[data-stream-caret]")).toBeNull();
    expect(stored.container.querySelector("[data-stream-word]")).toBeNull();
  });

  it("wraps only the words the server has sent, and no more appear on their own", () => {
    const view = render(<Markdown text="Built 3" streaming />);
    expect(view.container.querySelectorAll("[data-stream-word]")).toHaveLength(2);
    view.rerender(<Markdown text="Built 3 options" streaming />);
    expect(view.container.querySelectorAll("[data-stream-word]")).toHaveLength(3);
  });

  it("marks the heard-so-far line as streaming until the stored event replaces it", () => {
    const heard = chatReducer(chatStart("c1"), { type: "partial", text: "Built" });
    const last = shownLines(heard).at(-1);
    expect(last).toMatchObject({ kind: "agent", text: "Built", streaming: true });
  });
});

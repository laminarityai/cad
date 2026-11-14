import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "./Markdown";

describe("Markdown streaming", () => {
  it("keeps a word already shown when an inline token closes after it", () => {
    const { container, rerender } = render(<Markdown text="Built 3 options, see `a" streaming />);
    const built = [...container.querySelectorAll("[data-stream-word]")].find((one) => one.textContent === "Built");
    expect(built).toBeDefined();
    rerender(<Markdown text="Built 3 options, see `a`." streaming />);
    const after = [...container.querySelectorAll("[data-stream-word]")].find((one) => one.textContent === "Built");
    expect(after).toBe(built);
  });

  it("puts the caret inside the last paragraph, after the last word", () => {
    const { container } = render(<Markdown text="One two" streaming />);
    const caret = container.querySelector("[data-stream-caret]");
    expect(caret?.parentElement?.tagName).toBe("P");
  });
});

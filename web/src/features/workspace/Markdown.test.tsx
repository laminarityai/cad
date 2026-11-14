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

describe("Markdown table rows", () => {
  it("shows a row with no separator under it as text", () => {
    const { container } = render(<Markdown text={"Hi\n\n| a | b |"} />);
    expect(container.querySelector("table")).toBeNull();
    expect(container).toHaveTextContent("| a | b |");
  });

  it("turns a streamed header into a table once its separator comes", () => {
    const { container, rerender } = render(<Markdown text={"Options:\n\n| Option | Mass |"} streaming />);
    expect(container.querySelector("table")).toBeNull();
    rerender(<Markdown text={"Options:\n\n| Option | Mass |\n| --- | --- |\n| Slim | 12 g |"} streaming />);
    expect(container.querySelector("th")).toHaveTextContent("Option");
    expect(container.querySelector("td")).toHaveTextContent("Slim");
  });
});

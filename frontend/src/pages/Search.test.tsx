import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, it, expect } from "vitest";
import { Search } from "./Search";
vi.mock("../api", () => ({
  api: vi.fn(async (path: string) =>
    path === "/courses" || path.startsWith("/documents")
      ? []
      : {
          mode: "keyword",
          total: 21,
          hits: [
            {
              chunk_id: "x",
              document_id: "doc",
              version_id: "v1",
              title: "Lecture 1",
              kind: "pdf",
              locator_type: "page",
              locator: 3,
              text: "Gradient descent 梯度下降",
            },
          ],
        },
  ),
  locationLabel: () => "页 3",
}));
it("shows a result linking to the actual version and page", async () => {
  render(
    <MemoryRouter>
      <Search />
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "梯度下降" },
  });
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  await waitFor(() =>
    expect(screen.getByRole("link", { name: /Lecture 1/ })).toHaveAttribute(
      "href",
      "/documents/doc?version=v1&locator=3",
    ),
  );
  expect(screen.getByText("Gradient descent 梯度下降")).toBeInTheDocument();
});

it("clears old pages when criteria change", async () => {
  render(
    <MemoryRouter>
      <Search />
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "alpha" },
  });
  fireEvent.click(screen.getByRole("button", { name: "搜索" }));
  await screen.findByRole("button", { name: "加载更多" });
  fireEvent.change(screen.getByRole("searchbox"), {
    target: { value: "beta" },
  });
  expect(
    screen.queryByRole("button", { name: "加载更多" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: /Lecture 1/ }),
  ).not.toBeInTheDocument();
});

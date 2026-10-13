import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, it, expect } from "vitest";
import { Library } from "./Library";
vi.mock("../api", () => ({
  api: vi.fn(async (path: string) => (path.startsWith("/documents") ? [] : [])),
}));
import { api } from "../api";
it("uploads selected files as multipart data", async () => {
  render(
    <MemoryRouter>
      <Library />
    </MemoryRouter>,
  );
  fireEvent.change(screen.getByLabelText("选择资料文件"), {
    target: {
      files: [
        new File(["Gradient descent"], "lecture.md", { type: "text/markdown" }),
      ],
    },
  });
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/documents",
      expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
    ),
  );
});

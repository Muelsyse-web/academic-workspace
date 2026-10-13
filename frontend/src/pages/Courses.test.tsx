import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, it, expect } from "vitest";
import { Courses } from "./Courses";
vi.mock("../api", () => ({
  api: vi.fn(async () => []),
  post: vi.fn(async () => ({
    id: "new",
    name: "机器学习",
    code: "COMP3340",
    semester: "2026 Fall",
    color: "#3e6656",
  })),
}));
import { post } from "../api";
it("creates a named course from the accessible form", async () => {
  render(
    <MemoryRouter>
      <Courses />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "新建课程" }));
  fireEvent.change(screen.getByLabelText("课程名称"), {
    target: { value: "机器学习" },
  });
  fireEvent.change(screen.getByLabelText("课程代码"), {
    target: { value: "COMP3340" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存课程" }));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith(
      "/courses",
      expect.objectContaining({ name: "机器学习", code: "COMP3340" }),
    ),
  );
});

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, it, expect } from "vitest";
import { Learning } from "./Learning";
vi.mock("../api", () => ({
  api: vi.fn(async (path: string, options?: RequestInit) =>
    options?.method === "POST" ? { id: "c1" } : [],
  ),
  locationLabel: () => "页 1",
}));
import { api } from "../api";
it("creates a flashcard without an AI provider", async () => {
  render(
    <MemoryRouter>
      <Learning />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "新建卡片" }));
  fireEvent.change(screen.getByLabelText("卡片正面"), {
    target: { value: "什么是梯度？" },
  });
  fireEvent.change(screen.getByLabelText("卡片背面"), {
    target: { value: "偏导数组成的向量。" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存卡片" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/flashcards",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("什么是梯度"),
      }),
    ),
  );
});

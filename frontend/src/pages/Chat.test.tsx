import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, it, expect } from "vitest";
import { Chat } from "./Chat";
vi.mock("../api", () => ({
  api: vi.fn(async (path: string, options?: RequestInit) =>
    path === "/conversations/c1"
      ? {
          id: "c1",
          title: "Study",
          course_id: null,
          document_ids: [],
          messages: [],
        }
      : path === "/conversations/c1/messages"
        ? {
            id: "m1",
            status: "evidence_insufficient",
            content: "没有足够资料",
            sources: [],
          }
        : [],
  ),
  post: vi.fn(),
  locationLabel: () => "页 1",
}));
import { api } from "../api";
it("submits a question in the selected conversation", async () => {
  render(
    <MemoryRouter initialEntries={["/chat?id=c1"]}>
      <Chat />
    </MemoryRouter>,
  );
  const input = await screen.findByLabelText("向资料提问");
  fireEvent.change(input, { target: { value: "什么是梯度下降？" } });
  fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/conversations/c1/messages",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ content: "什么是梯度下降？" }),
      }),
    ),
  );
});

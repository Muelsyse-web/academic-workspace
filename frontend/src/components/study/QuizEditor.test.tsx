import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, it, expect } from "vitest";
import { QuizEditor } from "./QuizEditor";
import { blankQuestion } from "./types";
vi.mock("../../api", () => ({ api: vi.fn(async () => ({ id: "q" })) }));
import { api } from "../../api";
it("saves a manually authored choice quiz", async () => {
  render(
    <QuizEditor
      initial={{ title: "", course_id: null, questions: [blankQuestion()] }}
      courses={[]}
      onClose={() => {}}
      onSaved={() => {}}
    />,
  );
  fireEvent.change(screen.getByLabelText("练习标题"), {
    target: { value: "概率基础" },
  });
  fireEvent.change(screen.getByLabelText("第 1 题题干"), {
    target: { value: "P(A) 的取值范围？" },
  });
  fireEvent.change(screen.getByLabelText("第 1 题选项"), {
    target: { value: "0 到 1\n任意实数" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存练习" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/quizzes",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining("概率基础"),
      }),
    ),
  );
});

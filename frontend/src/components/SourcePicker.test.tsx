import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { SourcePicker } from "./SourcePicker";
import { api } from "../api";
vi.mock("../api", () => ({
  api: vi.fn(),
  locationLabel: (type: string, locator: number) => `${type} ${locator}`,
}));
const documents = [
  { id: "one", title: "One" },
  { id: "two", title: "Two" },
];
const unit = {
  id: "unit",
  version_id: "old-version",
  locator_type: "line",
  locator: 5,
  text: "Real original text.",
  heading: "",
};

it("discards a previous document selection while new units load and reports missing text", async () => {
  let finish!: (value: unknown) => void;
  vi.mocked(api).mockImplementation(async (path) =>
    path === "/documents"
      ? documents
      : path === "/documents/one/units"
        ? [unit]
        : new Promise((resolve) => {
            finish = resolve;
          }),
  );
  const onAdd = vi.fn();
  render(<SourcePicker onAdd={onAdd} onClose={vi.fn()} />);
  fireEvent.change(await screen.findByLabelText("选择资料"), {
    target: { value: "one" },
  });
  await screen.findByRole("option", { name: /Real original/ });
  fireEvent.change(screen.getByLabelText("选择原文位置"), {
    target: { value: "unit" },
  });
  expect(screen.getByRole("button", { name: "添加此引用" })).toBeEnabled();
  fireEvent.change(screen.getByLabelText("选择资料"), {
    target: { value: "two" },
  });
  expect(screen.queryByLabelText("引用摘录")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "添加此引用" })).toBeDisabled();
  expect(screen.getByRole("status")).toBeInTheDocument();
  finish([{ ...unit, id: "blank", text: "" }]);
  await screen.findByText("此资料没有可引用的文本，请先完成索引或检查扫描件。");
  expect(onAdd).not.toHaveBeenCalled();
});

it("shows unit request failures and cannot add stale references", async () => {
  vi.mocked(api).mockImplementation(async (path) => {
    if (path === "/documents") return documents;
    throw new Error("Index unavailable");
  });
  render(<SourcePicker onAdd={vi.fn()} onClose={vi.fn()} />);
  fireEvent.change(await screen.findByLabelText("选择资料"), {
    target: { value: "one" },
  });
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Index unavailable",
  );
  expect(screen.getByRole("button", { name: "添加此引用" })).toBeDisabled();
});

it("submits actual immutable unit metadata with a continuous excerpt", async () => {
  vi.mocked(api).mockImplementation(async (path) =>
    path === "/documents" ? documents : [unit],
  );
  const onAdd = vi.fn(),
    onClose = vi.fn();
  render(<SourcePicker onAdd={onAdd} onClose={onClose} />);
  fireEvent.change(await screen.findByLabelText("选择资料"), {
    target: { value: "one" },
  });
  await screen.findByRole("option", { name: /Real original/ });
  fireEvent.change(screen.getByLabelText("选择原文位置"), {
    target: { value: "unit" },
  });
  fireEvent.change(screen.getByLabelText("引用摘录"), {
    target: { value: "original" },
  });
  fireEvent.click(screen.getByRole("button", { name: "添加此引用" }));
  await waitFor(() =>
    expect(onAdd).toHaveBeenCalledWith({
      document_id: "one",
      version_id: "old-version",
      locator_type: "line",
      locator: 5,
      quote: "original",
      document_title: "One",
    }),
  );
  expect(onClose).toHaveBeenCalledOnce();
});

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

const existingSource = {
  document_id: "doc1",
  version_id: "v1",
  locator_type: "page",
  locator: 1,
  quote: "first quote",
  document_title: "First document",
};
const existingNote = {
  id: "existing",
  title: "Existing note",
  body: "[[Same]]",
  course_id: null,
  topic: "",
  tags: [],
  sources: [existingSource],
  outgoing_links: [],
  backlinks: [],
  unresolved_links: [{ raw_title: "Same", reason: "ambiguous" }],
};
function notesApi() {
  let saved = structuredClone(existingNote) as Omit<
    typeof existingNote,
    "outgoing_links"
  > & { outgoing_links: { id: string; title: string }[] };
  vi.mocked(api).mockImplementation(async (path, options) => {
    if (path === "/courses") return [];
    if (path === "/documents")
      return [{ id: "doc2", title: "Second document", active_version: "v2" }];
    if (path === "/documents/doc2/units")
      return [
        {
          id: "fragment1",
          version_id: "v2",
          locator_type: "paragraph",
          locator: 4,
          heading: "",
          text: "First fragment of shared location.",
        },
        {
          id: "fragment2",
          version_id: "v2",
          locator_type: "paragraph",
          locator: 4,
          heading: "",
          text: "Second fragment with verified quote.",
        },
      ];
    if (options?.method === "PATCH") {
      saved = { ...saved, ...JSON.parse(options.body as string) };
      return saved;
    }
    if (options?.method === "PUT") {
      saved = {
        ...saved,
        outgoing_links: [{ id: "target2", title: "Same" }],
        unresolved_links: [],
      };
      return saved;
    }
    if (path === "/notes/existing") return saved;
    if (path === "/notes")
      return [
        { id: "target1", title: "Same" },
        { id: "target2", title: "Same" },
      ];
    if (path.startsWith("/notes?")) return [saved];
    throw new Error("Unexpected API: " + path);
  });
}

it("appends a verified source from a second document to an existing note and saves both sources", async () => {
  notesApi();
  render(
    <MemoryRouter initialEntries={["/notes?id=existing"]}>
      <Notes />
    </MemoryRouter>,
  );
  await screen.findByDisplayValue("Existing note");
  fireEvent.click(screen.getByRole("button", { name: "添加资料引用" }));
  fireEvent.change(await screen.findByLabelText("选择资料"), {
    target: { value: "doc2" },
  });
  await screen.findByRole("option", { name: /Second fragment/ });
  fireEvent.change(screen.getByLabelText("选择原文位置"), {
    target: { value: "fragment2" },
  });
  expect(screen.getByLabelText("引用摘录")).toHaveValue(
    "Second fragment with verified quote.",
  );
  fireEvent.change(screen.getByLabelText("引用摘录"), {
    target: { value: "invented quote" },
  });
  expect(screen.getByRole("button", { name: "添加此引用" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("引用摘录"), {
    target: { value: "verified quote" },
  });
  fireEvent.click(screen.getByRole("button", { name: "添加此引用" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByText("未保存")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "保存笔记" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith(
      "/notes/existing",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          title: "Existing note",
          body: "[[Same]]",
          course_id: null,
          topic: "",
          tags: [],
          sources: [
            {
              document_id: "doc1",
              version_id: "v1",
              locator_type: "page",
              locator: 1,
              quote: "first quote",
            },
            {
              document_id: "doc2",
              version_id: "v2",
              locator_type: "paragraph",
              locator: 4,
              quote: "verified quote",
            },
          ],
        }),
      }),
    ),
  );
});

it("chooses an explicit target from all notes, independent of the list filter", async () => {
  notesApi();
  render(
    <MemoryRouter initialEntries={["/notes?id=existing"]}>
      <Notes />
    </MemoryRouter>,
  );
  await screen.findByDisplayValue("Existing note");
  fireEvent.change(screen.getByLabelText("搜索笔记"), {
    target: { value: "Existing" },
  });
  const choice = await screen.findByLabelText("为 [[Same]] 选择目标笔记");
  await waitFor(() =>
    expect(choice.querySelectorAll("option")).toHaveLength(3),
  );
  fireEvent.change(choice, { target: { value: "target2" } });
  fireEvent.click(screen.getByRole("button", { name: "确认链接 [[Same]]" }));
  await waitFor(() =>
    expect(api).toHaveBeenCalledWith("/notes/existing/links", {
      method: "PUT",
      body: JSON.stringify({ raw_title: "Same", target_id: "target2" }),
    }),
  );
  await waitFor(() =>
    expect(
      screen.queryByLabelText("为 [[Same]] 选择目标笔记"),
    ).not.toBeInTheDocument(),
  );
  expect(screen.getByLabelText("Markdown 内容")).toHaveValue("[[Same]]");
});

it("requires saving dirty content before rebinding links", async () => {
  notesApi();
  render(
    <MemoryRouter initialEntries={["/notes?id=existing"]}>
      <Notes />
    </MemoryRouter>,
  );
  await screen.findByDisplayValue("Existing note");
  fireEvent.change(screen.getByLabelText("Markdown 内容"), {
    target: { value: "Unsaved [[Same]]" },
  });
  expect(
    await screen.findByLabelText("为 [[Same]] 选择目标笔记"),
  ).toBeDisabled();
  expect(
    screen.getByText("请先保存笔记，再选择链接目标。"),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Markdown 内容")).toHaveValue(
    "Unsaved [[Same]]",
  );
});

it("preserves edits made while a link binding request is pending", async () => {
  notesApi();
  const ordinary = vi.mocked(api).getMockImplementation()!;
  let finish!: (value: unknown) => void;
  vi.mocked(api).mockImplementation((path, options) =>
    options?.method === "PUT"
      ? new Promise((resolve) => {
          finish = resolve;
        })
      : ordinary(path, options),
  );
  render(
    <MemoryRouter initialEntries={["/notes?id=existing"]}>
      <Notes />
    </MemoryRouter>,
  );
  await screen.findByDisplayValue("Existing note");
  fireEvent.change(screen.getByLabelText("为 [[Same]] 选择目标笔记"), {
    target: { value: "target2" },
  });
  fireEvent.click(screen.getByRole("button", { name: "确认链接 [[Same]]" }));
  fireEvent.change(screen.getByLabelText("Markdown 内容"), {
    target: { value: "New edits [[Same]]" },
  });
  finish({
    ...existingNote,
    outgoing_links: [{ id: "target2", title: "Same" }],
    unresolved_links: [],
  });
  await waitFor(() =>
    expect(
      screen.queryByLabelText("为 [[Same]] 选择目标笔记"),
    ).not.toBeInTheDocument(),
  );
  expect(screen.getByLabelText("Markdown 内容")).toHaveValue(
    "New edits [[Same]]",
  );
  expect(screen.getByText("未保存")).toBeInTheDocument();
});

it("keeps reader-created sources and allows another document before the first save", async () => {
  notesApi();
  render(
    <MemoryRouter
      initialEntries={[
        {
          pathname: "/notes",
          state: { source: existingSource, title: "Reader note" },
        },
      ]}
    >
      <Notes />
    </MemoryRouter>,
  );
  expect(await screen.findByDisplayValue("Reader note")).toBeInTheDocument();
  expect(screen.getByLabelText("Markdown 内容")).toHaveValue("> first quote");
  fireEvent.click(screen.getByRole("button", { name: "添加资料引用" }));
  fireEvent.change(await screen.findByLabelText("选择资料"), {
    target: { value: "doc2" },
  });
  await screen.findByRole("option", { name: /Second fragment/ });
  fireEvent.change(screen.getByLabelText("选择原文位置"), {
    target: { value: "fragment2" },
  });
  fireEvent.click(screen.getByRole("button", { name: "添加此引用" }));
  expect(screen.getAllByRole("button", { name: "移除引用" })).toHaveLength(2);
  expect(screen.getByText("未保存")).toBeInTheDocument();
  expect(screen.getByLabelText("Markdown 内容")).toHaveValue("> first quote");
});

import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { Plus, Save, Download, Trash2, Link2 } from "lucide-react";
import { api, locationLabel, type Course } from "../api";
import {
  useData,
  PageHeading,
  ErrorMessage,
  Empty,
} from "../components/Shared";
import { Markdown } from "../components/Markdown";
type Source = {
  document_id: string;
  version_id: string;
  locator_type: string;
  locator: number;
  quote: string;
  document_title?: string;
};
type Note = {
  id: string;
  title: string;
  body: string;
  course_id: string | null;
  topic: string;
  tags: string[];
  sources: Source[];
  outgoing_links: { id: string; title: string }[];
  backlinks: { id: string; title: string }[];
  unresolved_links: { raw_title: string; reason: string }[];
};
const blank = (): Note => ({
  id: "",
  title: "",
  body: "",
  course_id: null,
  topic: "",
  tags: [],
  sources: [],
  outgoing_links: [],
  backlinks: [],
  unresolved_links: [],
});
export function Notes() {
  const location = useLocation(),
    [params, setParams] = useSearchParams(),
    [revision, setRevision] = useState(0),
    [query, setQuery] = useState(""),
    [course, setCourse] = useState(""),
    [note, setNote] = useState<Note>(blank),
    [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [status, setStatus] = useState("");
  const id = params.get("id") || "";
  const filters = new URLSearchParams({ q: query });
  if (course) filters.set("course_id", course);
  const { data: notes, error: listError } = useData<Note[]>(
      "/notes?" + filters,
      [],
      revision,
    ),
    { data: courses } = useData<Course[]>("/courses", []);
  useEffect(() => {
    let active = true;
    if (id) {
      api<Note>("/notes/" + id)
        .then((n) => {
          if (active) {
            setNote(n);
            setDirty(false);
            setStatus("已保存");
          }
        })
        .catch((e) => setError(e.message));
    } else {
      const source = location.state?.source as Source | undefined;
      setNote({
        ...blank(),
        ...(source
          ? {
              title: location.state.title || "引用笔记",
              body: "> " + source.quote,
              sources: [source],
              course_id: location.state.course_id || null,
            }
          : {}),
      });
      setDirty(Boolean(source));
      setStatus("");
    }
    return () => {
      active = false;
    };
  }, [id, location.state]);
  useEffect(() => {
    if (!dirty) return;
    const unload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const leave = (event: MouseEvent) => {
      const anchor = (event.target as Element).closest?.("a");
      if (
        anchor?.getAttribute("href")?.startsWith("#") &&
        !confirm("笔记有未保存的内容，确定离开？")
      )
        event.preventDefault();
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", leave, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("click", leave, true);
    };
  }, [dirty]);
  function edit(update: Partial<Note>) {
    setNote((n) => ({ ...n, ...update }));
    setDirty(true);
    setStatus("未保存");
  }
  function choose(identifier: string) {
    if (dirty && !confirm("放弃未保存的修改？")) return;
    setError("");
    if (identifier) setParams({ id: identifier });
    else {
      setParams({});
      setNote(blank());
      setDirty(false);
      setStatus("");
    }
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = {
        title: note.title,
        body: note.body,
        course_id: note.course_id,
        topic: note.topic,
        tags: note.tags,
        sources: note.sources.map(({ document_title, ...source }) => source),
      };
      const saved = await api<Note>(note.id ? "/notes/" + note.id : "/notes", {
        method: note.id ? "PATCH" : "POST",
        body: JSON.stringify(body),
      });
      setNote(saved);
      setDirty(false);
      setStatus("已保存");
      setRevision((v) => v + 1);
      setParams({ id: saved.id });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!note.id || !confirm("删除这篇笔记？")) return;
    try {
      await api("/notes/" + note.id, { method: "DELETE" });
      setDirty(false);
      setNote(blank());
      setParams({});
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="MAKE KNOWLEDGE YOUR OWN"
        title="学习笔记"
        description="把原文证据与自己的理解写在一起。使用 [[笔记标题]] 连接想法。"
        action={
          <button className="primary" onClick={() => choose("")}>
            <Plus size={17} />
            新建笔记
          </button>
        }
      />
      <ErrorMessage error={error || listError} />
      <div className="notes-layout">
        <aside className="notes-sidebar">
          <input
            aria-label="搜索笔记"
            type="search"
            placeholder="搜索笔记…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <select
            aria-label="笔记课程筛选"
            value={course}
            onChange={(e) => setCourse(e.target.value)}
          >
            <option value="">全部课程</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <div className="note-list">
            {notes.map((n) => (
              <button
                key={n.id}
                className={note.id === n.id ? "selected" : ""}
                onClick={() => choose(n.id)}
              >
                <strong>{n.title}</strong>
                <small>{n.body.slice(0, 65) || "空白笔记"}</small>
              </button>
            ))}
            {!notes.length && (
              <p className="panel-message">还没有匹配的笔记。</p>
            )}
          </div>
          <a className="button" href="/api/v1/notes/export">
            <Download size={15} />
            导出全部笔记
          </a>
        </aside>
        <form className="note-workbench" onSubmit={save}>
          <div className="note-toolbar">
            <span className={"save-status " + (dirty ? "unsaved" : "")}>
              {status || "新笔记"}
            </span>
            <div className="button-group">
              {note.id && (
                <>
                  <a
                    className="button"
                    href={"/api/v1/notes/" + note.id + "/export"}
                  >
                    <Download size={15} />
                    Markdown
                  </a>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="删除笔记"
                    onClick={remove}
                  >
                    <Trash2 size={16} />
                  </button>
                </>
              )}
              <button className="primary" disabled={busy}>
                <Save size={16} />
                {busy ? "保存中…" : "保存笔记"}
              </button>
            </div>
          </div>
          <input
            className="note-title-input"
            aria-label="笔记标题"
            value={note.title}
            onChange={(e) => edit({ title: e.target.value })}
            placeholder="给这个想法一个标题"
            required
            maxLength={500}
          />
          <div className="filters">
            <select
              aria-label="关联课程"
              value={note.course_id || ""}
              onChange={(e) => edit({ course_id: e.target.value || null })}
            >
              <option value="">不限定课程</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <input
              aria-label="笔记主题"
              placeholder="知识主题"
              value={note.topic}
              onChange={(e) => edit({ topic: e.target.value })}
            />
            <input
              aria-label="笔记标签"
              placeholder="标签，用逗号分隔"
              value={note.tags.join(",")}
              onChange={(e) =>
                edit({
                  tags: e.target.value
                    .split(",")
                    .map((t) => t.trim())
                    .filter(Boolean),
                })
              }
            />
          </div>
          <div className="editor-split">
            <div>
              <span className="editor-label">MARKDOWN</span>
              <textarea
                aria-label="Markdown 内容"
                value={note.body}
                onChange={(e) => edit({ body: e.target.value })}
                placeholder={
                  "从你的理解开始…\n\n支持 $LaTeX$、代码、表格和 [[双向链接]]。"
                }
              />
            </div>
            <div className="note-preview">
              <span className="editor-label">实时预览</span>
              {note.body ? (
                <Markdown text={note.body} />
              ) : (
                <p className="panel-message">写下内容，这里会显示阅读效果。</p>
              )}
            </div>
          </div>
          <div className="note-connections">
            <h3>
              <Link2 size={16} />
              资料引用
            </h3>
            {note.sources.length ? (
              note.sources.map((s, index) => (
                <div className="citation-card" key={index}>
                  <Link
                    to={`/documents/${s.document_id}?version=${s.version_id}&locator=${s.locator}`}
                  >
                    {s.document_title || "原始资料"} ·{" "}
                    {locationLabel(s.locator_type, s.locator)}
                  </Link>
                  <blockquote>{s.quote}</blockquote>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() =>
                      edit({
                        sources: note.sources.filter((_, i) => i !== index),
                      })
                    }
                  >
                    移除引用
                  </button>
                </div>
              ))
            ) : (
              <p className="subtle">
                在资料阅读页选择“创建引用笔记”，即可保留可追溯的原文片段。
              </p>
            )}
            <div className="links-grid">
              <div>
                <h3>引用的笔记</h3>
                {note.outgoing_links.map((n) => (
                  <Link key={n.id} to={"/notes?id=" + n.id}>
                    {n.title}
                  </Link>
                ))}
              </div>
              <div>
                <h3>反向链接</h3>
                {note.backlinks.map((n) => (
                  <Link key={n.id} to={"/notes?id=" + n.id}>
                    {n.title}
                  </Link>
                ))}
              </div>
            </div>
            {note.unresolved_links.map((n, index) => (
              <p className="subtle" key={index}>
                [[{n.raw_title}]] ·{" "}
                {n.reason === "ambiguous"
                  ? "有多个同名笔记"
                  : n.reason === "deleted"
                    ? "原目标已删除"
                    : "目标尚未创建"}
              </p>
            ))}
          </div>
        </form>
      </div>
    </>
  );
}

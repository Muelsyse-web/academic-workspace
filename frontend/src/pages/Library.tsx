import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Upload, FolderUp, Star, ArrowUpRight, RefreshCw } from "lucide-react";
import { api, type Course, type Document } from "../api";
import {
  PageHeading,
  ErrorMessage,
  Empty,
  Loading,
  useData,
} from "../components/Shared";
const labels: Record<string, string> = {
  ready: "已索引",
  queued: "排队中",
  processing: "正在解析",
  failed: "解析失败",
  needs_attention: "缺少文本",
};
export function Library() {
  const [params] = useSearchParams(),
    [course, setCourse] = useState(params.get("course") || ""),
    [kind, setKind] = useState(""),
    [query, setQuery] = useState(""),
    [revision, setRevision] = useState(0),
    [uploading, setUploading] = useState(false),
    [error, setError] = useState(""),
    [drag, setDrag] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null),
    folderInput = useRef<HTMLInputElement>(null);
  const {
    data: docs,
    error: loadError,
    loading,
  } = useData<Document[]>(
    "/documents?" + new URLSearchParams({ course_id: course, kind, q: query }),
    [],
    revision,
  );
  const { data: courses } = useData<Course[]>("/courses", []);
  const active = docs.some((d) => ["queued", "processing"].includes(d.status));
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setRevision((v) => v + 1), 1500);
    return () => clearInterval(timer);
  }, [active]);
  async function upload(files: FileList | File[] | null) {
    if (!files?.length) return;
    setUploading(true);
    setError("");
    const accepted = Array.from(files).filter((file) =>
      /\.(pdf|pptx|docx|txt|md)$/i.test(file.name),
    );
    if (!accepted.length) {
      setError("请选择 PDF、PPTX、DOCX、TXT 或 Markdown 文件。");
      setUploading(false);
      return;
    }
    try {
      for (let start = 0; start < accepted.length; start += 100) {
        const form = new FormData();
        accepted
          .slice(start, start + 100)
          .forEach((file) =>
            form.append("files", file, file.webkitRelativePath || file.name),
          );
        form.append("course_id", course);
        await api("/documents", { method: "POST", body: form });
      }
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
      if (folderInput.current) folderInput.current.value = "";
    }
  }
  async function favorite(doc: Document) {
    try {
      await api("/documents/" + doc.id, {
        method: "PATCH",
        body: JSON.stringify({ favorite: !doc.favorite }),
      });
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="A HOME FOR YOUR SOURCES"
        title="学术资料库"
        description="讲义、论文和课程笔记，集中管理，保留每一份原件。"
        action={
          <button
            className="primary"
            disabled={uploading}
            onClick={() => fileInput.current?.click()}
          >
            <Upload size={17} />
            {uploading ? "正在上传…" : "导入资料"}
          </button>
        }
      />
      <input
        ref={fileInput}
        className="sr-only"
        type="file"
        aria-label="选择资料文件"
        accept=".pdf,.pptx,.docx,.txt,.md"
        multiple
        onChange={(e) => upload(e.target.files)}
      />
      <input
        ref={folderInput}
        className="sr-only"
        type="file"
        aria-label="选择资料文件夹"
        {...{ webkitdirectory: "" }}
        multiple
        onChange={(e) => upload(e.target.files)}
      />
      <div
        className={"dropzone " + (drag ? "dragging" : "")}
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          if (!uploading) void upload(e.dataTransfer.files);
        }}
      >
        <span className="upload-symbol">
          <Upload size={24} />
        </span>
        <div>
          <strong>把资料拖到这里</strong>
          <p>PDF · PPTX · DOCX · TXT · Markdown，每份最多 100 MiB</p>
        </div>
        <button
          onClick={() => folderInput.current?.click()}
          disabled={uploading}
        >
          <FolderUp size={16} />
          导入文件夹
        </button>
      </div>
      <div className="filters library-filters">
        <input
          type="search"
          placeholder="按标题筛选…"
          aria-label="筛选资料标题"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          value={course}
          aria-label="资料课程"
          onChange={(e) => setCourse(e.target.value)}
        >
          <option value="">全部课程</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select
          value={kind}
          aria-label="资料格式"
          onChange={(e) => setKind(e.target.value)}
        >
          <option value="">全部格式</option>
          {["pdf", "pptx", "docx", "txt", "md"].map((k) => (
            <option key={k} value={k}>
              {k.toUpperCase()}
            </option>
          ))}
        </select>
        <button
          aria-label="刷新资料"
          className="icon-button"
          onClick={() => setRevision((v) => v + 1)}
        >
          <RefreshCw size={17} />
        </button>
      </div>
      <ErrorMessage error={error || loadError} />
      <div className="section-heading">
        <h2>
          全部资料 <span className="count">{docs.length}</span>
        </h2>
        {active && <span className="subtle">索引任务处理中…</span>}
      </div>
      {loading && !docs.length ? (
        <Loading />
      ) : docs.length ? (
        <div className="panel document-table">
          {docs.map((doc) => (
            <div className="document-row" key={doc.id}>
              <span className={"file-badge " + doc.kind}>
                {doc.kind.toUpperCase()}
              </span>
              <Link className="grow" to={"/documents/" + doc.id}>
                <strong>{doc.title}</strong>
                <small>
                  {doc.topic || doc.filename} {doc.tags.map((t) => " · " + t)}
                </small>
              </Link>
              <span className={"status " + doc.status}>
                {labels[doc.status] || doc.status}
              </span>
              <button
                className={"icon-button " + (doc.favorite ? "favorited" : "")}
                aria-label={"收藏 " + doc.title}
                aria-pressed={doc.favorite}
                onClick={() => favorite(doc)}
              >
                <Star size={17} fill={doc.favorite ? "currentColor" : "none"} />
              </button>
              <Link
                aria-label={"打开 " + doc.title}
                to={"/documents/" + doc.id}
              >
                <ArrowUpRight size={18} />
              </Link>
            </div>
          ))}
        </div>
      ) : (
        <Empty
          title="资料库准备好了"
          description="选择课程后导入资料。系统会保留原件，并为每个片段建立可追溯的位置。"
        />
      )}
    </>
  );
}

import { useEffect, useState, type FormEvent } from "react";
import {
  Link,
  useParams,
  useSearchParams,
  useNavigate,
} from "react-router-dom";
import { ArrowLeft, Download, RefreshCw, FileText } from "lucide-react";
import {
  api,
  post,
  locationLabel,
  type Document,
  type Course,
  type SourceUnit,
} from "../api";
import { useData, ErrorMessage, Loading, Modal } from "../components/Shared";
export function DocumentView() {
  const navigate = useNavigate();
  const { id } = useParams(),
    [params] = useSearchParams(),
    [revision, setRevision] = useState(0),
    [page, setPage] = useState(Number(params.get("locator") || 1)),
    [error, setError] = useState(""),
    [editing, setEditing] = useState(false);
  const version = params.get("version") || "",
    { data: doc, error: loadError } = useData<Document | null>(
      "/documents/" + id,
      null,
      revision,
    );
  const { data: units } = useData<SourceUnit[]>(
      `/documents/${id}/units?version_id=${version}`,
      [],
      revision,
    ),
    { data: courses } = useData<Course[]>("/courses", []);
  const { data: allDocuments } = useData<Document[]>(
    "/documents",
    [],
    revision,
  );
  const { data: images, error: imageError } = useData<
    { index: number; width: number; height: number; url: string; alt: string }[]
  >(doc?.kind === "pptx" ? `/documents/${id}/slides/${page}/images` : null, []);
  const requestedLocation = params.get("locator");
  useEffect(
    () => setPage(Number(requestedLocation || 1)),
    [id, version, requestedLocation],
  );
  useEffect(() => {
    if (!doc || !["queued", "processing"].includes(doc.status)) return;
    const timer = setInterval(() => setRevision((v) => v + 1), 1200);
    return () => clearInterval(timer);
  }, [doc]);
  async function reindex() {
    try {
      await post("/documents/" + id + "/reindex", {});
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await api("/documents/" + id, {
        method: "PATCH",
        body: JSON.stringify({
          title: f.get("title"),
          topic: f.get("topic"),
          tags: String(f.get("tags"))
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean),
          course_ids: f.getAll("courses"),
          related_ids: f.getAll("related"),
        }),
      });
      setEditing(false);
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  const selected = units.filter((u) => u.locator === page);
  return (
    <>
      <Link className="back-link" to="/library">
        <ArrowLeft size={16} />
        返回资料库
      </Link>
      <ErrorMessage error={error || loadError} />
      {!doc ? (
        <Loading />
      ) : (
        <>
          <div className="document-heading">
            <div>
              <span className="eyebrow">
                {doc.kind.toUpperCase()} · SOURCE READER
              </span>
              <h1>{doc.title}</h1>
              <p>
                {doc.relative_path || doc.filename}
                {version && version !== doc.active_version
                  ? " · 历史引用版本"
                  : ""}
              </p>
            </div>
            <div className="button-group">
              <button onClick={() => setEditing(true)}>编辑信息</button>
              <button
                onClick={reindex}
                disabled={["queued", "processing"].includes(doc.status)}
              >
                <RefreshCw size={16} />
                重新索引
              </button>
              <a
                className="button"
                href={"/api/v1/documents/" + id + "/original?download=true"}
              >
                <Download size={16} />
                原件
              </a>
            </div>
          </div>
          {doc.error && <ErrorMessage error={doc.error} />}
          <div className="reader-layout">
            <aside className="source-nav">
              <h3>
                <FileText size={16} />
                内容位置
              </h3>
              {units.map((u) => (
                <button
                  key={u.id}
                  className={page === u.locator ? "selected" : ""}
                  onClick={() => setPage(u.locator)}
                >
                  {locationLabel(u.locator_type, u.locator)}
                  <small>
                    {u.heading || u.text.slice(0, 36) || "此处没有可提取文本"}
                  </small>
                </button>
              ))}
            </aside>
            <div className="source-content">
              {doc.kind === "pdf" && (
                <iframe
                  key={page}
                  title="PDF 原文预览"
                  src={`/api/v1/documents/${id}/original#page=${page}`}
                  className="pdf-viewer"
                />
              )}
              {doc.kind === "pptx" && (
                <>
                  <ErrorMessage error={imageError} />
                  <div className="slide-images">
                    {images.map((image) => (
                      <figure key={image.index}>
                        <img src={image.url} alt={image.alt} loading="lazy" />
                        <figcaption>{image.alt}</figcaption>
                      </figure>
                    ))}
                  </div>
                </>
              )}
              <div className="extraction-label">
                {doc.kind === "pdf"
                  ? "本页提取文本"
                  : "内容提取预览 · Office 排版请下载原件查看"}
              </div>
              {selected.length ? (
                selected.map((u) => (
                  <section key={u.id} className="source-unit">
                    {u.text && (
                      <button
                        className="text-button"
                        onClick={() => {
                          const selection = window.getSelection()?.toString();
                          navigate("/notes", {
                            state: {
                              title: doc.title + " · 笔记",
                              course_id: doc.course_ids[0],
                              source: {
                                document_id: doc.id,
                                version_id: u.version_id,
                                locator_type: u.locator_type,
                                locator: u.locator,
                                quote:
                                  selection && u.text.includes(selection)
                                    ? selection
                                    : u.text.slice(0, 2000),
                                document_title: doc.title,
                              },
                            },
                          });
                        }}
                      >
                        创建引用笔记
                      </button>
                    )}
                    <span className="pill">
                      {locationLabel(u.locator_type, u.locator)}
                    </span>
                    <pre>
                      {u.text || "没有可提取文本；扫描件需要后续 OCR。"}
                    </pre>
                  </section>
                ))
              ) : (
                <p className="panel-message">
                  {["queued", "processing"].includes(doc.status)
                    ? "正在解析，请稍候…"
                    : "此位置暂无可提取内容。"}
                </p>
              )}
            </div>
          </div>
          {doc.related_ids.length > 0 && (
            <section className="panel" style={{ marginTop: 20, padding: 20 }}>
              <h3>关联资料</h3>
              {allDocuments
                .filter((d) => doc.related_ids.includes(d.id))
                .map((d) => (
                  <Link className="button" key={d.id} to={"/documents/" + d.id}>
                    {d.title}
                  </Link>
                ))}
            </section>
          )}
          <Modal
            open={editing}
            onClose={() => setEditing(false)}
            title="资料信息"
          >
            <form className="form-stack" onSubmit={save}>
              <label>
                标题
                <input name="title" defaultValue={doc.title} required />
              </label>
              <label>
                知识主题
                <input name="topic" defaultValue={doc.topic} />
              </label>
              <label>
                标签（逗号分隔）
                <input name="tags" defaultValue={doc.tags.join(", ")} />
              </label>
              <fieldset>
                <legend>关联课程</legend>
                {courses.map((c) => (
                  <label className="checkbox-label" key={c.id}>
                    <input
                      type="checkbox"
                      name="courses"
                      value={c.id}
                      defaultChecked={doc.course_ids.includes(c.id)}
                    />
                    {c.name}
                  </label>
                ))}
              </fieldset>
              <fieldset>
                <legend>关联资料</legend>
                <div className="document-picker">
                  {allDocuments
                    .filter((d) => d.id !== doc.id)
                    .map((d) => (
                      <label className="checkbox-label" key={d.id}>
                        <input
                          type="checkbox"
                          name="related"
                          value={d.id}
                          defaultChecked={doc.related_ids.includes(d.id)}
                        />
                        {d.title}
                      </label>
                    ))}
                </div>
              </fieldset>
              <button className="primary">保存资料信息</button>
            </form>
          </Modal>
        </>
      )}
    </>
  );
}

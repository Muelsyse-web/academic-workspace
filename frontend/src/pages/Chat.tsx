import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Plus,
  Send,
  MessageSquare,
  Trash2,
  Square,
  BookOpen,
} from "lucide-react";
import {
  api,
  locationLabel,
  type Course,
  type Document,
  type SearchHit,
} from "../api";
import {
  useData,
  PageHeading,
  Modal,
  ErrorMessage,
  Loading,
  Empty,
} from "../components/Shared";
import { Markdown } from "../components/Markdown";
type Message = {
  id: string;
  role: string;
  content: string;
  status: string;
  sources: (SearchHit & { quote: string })[];
};
type Conversation = {
  id: string;
  title: string;
  course_id: string | null;
  document_ids: string[];
  messages?: Message[];
};
const statuses: Record<string, string> = {
  citations_verified: "引用已核验，可打开原文检查",
  unverified: "未通过引用核验，请勿将其当作有来源的结论",
  evidence_insufficient: "证据不足",
  provider_error: "本地模型不可用",
  cancelled: "已取消",
};
export function Chat() {
  const [params, setParams] = useSearchParams(),
    id = params.get("id") || "",
    [revision, setRevision] = useState(0),
    [open, setOpen] = useState(false),
    [draft, setDraft] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [course, setCourse] = useState("");
  const { data: conversations } = useData<Conversation[]>(
      "/conversations",
      [],
      revision,
    ),
    { data: courses } = useData<Course[]>("/courses", []),
    { data: documents } = useData<Document[]>(
      "/documents?course_id=" + course,
      [],
    );
  const {
    data: conversation,
    error: loadError,
    loading,
  } = useData<Conversation | null>(
    id ? "/conversations/" + id : null,
    null,
    revision,
  );
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    try {
      const created = await api<Conversation>("/conversations", {
        method: "POST",
        body: JSON.stringify({
          title: values.get("title"),
          course_id: course || null,
          document_ids: values.getAll("documents"),
        }),
      });
      setParams({ id: created.id });
      setOpen(false);
      setDraft("");
      setRevision((v) => v + 1);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    if (!id || !draft.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await api<Message>("/conversations/" + id + "/messages", {
        method: "POST",
        body: JSON.stringify({ content: draft }),
      });
      setDraft("");
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove() {
    if (!confirm("删除这段对话和历史记录？")) return;
    try {
      await api("/conversations/" + id, { method: "DELETE" });
      setParams({});
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="ASK WITH EVIDENCE"
        title="AI 学术问答"
        description="让本地模型基于你的课程资料回答，并把每条引用交还给原文。"
        action={
          <button className="primary" onClick={() => setOpen(true)}>
            <Plus size={17} />
            新建对话
          </button>
        }
      />
      <ErrorMessage error={error || (id ? loadError : "")} />
      <div className="chat-layout">
        <aside className="chat-sidebar">
          <span className="eyebrow">对话历史</span>
          {conversations.map((c) => (
            <button
              key={c.id}
              className={id === c.id ? "selected" : ""}
              disabled={busy}
              onClick={() => {
                setParams({ id: c.id });
                setDraft("");
                setError("");
              }}
            >
              <MessageSquare size={16} />
              <span>
                {c.title}
                <small>
                  {c.document_ids.length
                    ? `${c.document_ids.length} 份指定资料`
                    : c.course_id
                      ? "课程范围"
                      : "整个知识库"}
                </small>
              </span>
            </button>
          ))}
          {!conversations.length && (
            <p className="panel-message">从一个概念或问题开始。</p>
          )}
          <Link className="button" to="/settings">
            配置本地模型
          </Link>
        </aside>
        <section className="chat-workbench">
          {!id ? (
            <Empty
              title="有来源，才有依据"
              description="新建对话并指定课程或资料。模型未启动时，你仍可以管理资料、写笔记和复习。"
              action={
                <button onClick={() => setOpen(true)}>开始一次学习对话</button>
              }
            />
          ) : loading && !conversation ? (
            <Loading />
          ) : (
            <>
              <div className="chat-heading">
                <div>
                  <h2>{conversation?.title}</h2>
                  <small>
                    {conversation?.document_ids.length
                      ? "已限制指定资料"
                      : conversation?.course_id
                        ? "已限制课程资料"
                        : "检索整个知识库"}
                  </small>
                </div>
                <button
                  aria-label="删除对话"
                  className="icon-button"
                  onClick={remove}
                  disabled={busy}
                >
                  <Trash2 size={17} />
                </button>
              </div>
              <div className="messages">
                {conversation?.messages?.length ? (
                  conversation.messages.map((m) => (
                    <article key={m.id} className={"message " + m.role}>
                      <span className="eyebrow">
                        {m.role === "user" ? "YOU" : "SCHOLAR · LOCAL AI"}
                      </span>
                      <Markdown text={m.content} />
                      {m.role === "assistant" && (
                        <>
                          <div className={"answer-status " + m.status}>
                            {statuses[m.status] || m.status}
                          </div>
                          {m.sources.map((source, index) => (
                            <details
                              className="citation-card"
                              key={source.chunk_id + "-" + index}
                            >
                              <summary>
                                <BookOpen size={14} />[{index + 1}]{" "}
                                {source.title} ·{" "}
                                {locationLabel(
                                  source.locator_type,
                                  source.locator,
                                )}
                              </summary>
                              <blockquote>{source.quote}</blockquote>
                              <Link
                                to={`/documents/${source.document_id}?version=${source.version_id}&locator=${source.locator}`}
                              >
                                打开实际来源 →
                              </Link>
                            </details>
                          ))}
                        </>
                      )}
                    </article>
                  ))
                ) : (
                  <div className="chat-welcome">
                    <MessageSquare size={30} />
                    <h3>你的资料，准备好被提问了。</h3>
                    <p>
                      试试“解释 gradient descent”或“这些资料如何定义条件概率”。
                    </p>
                  </div>
                )}
                {busy && <Loading />}
              </div>
              <form className="chat-composer" onSubmit={send}>
                <textarea
                  aria-label="向资料提问"
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  placeholder="提出问题，或要求结合原文推导一个公式…"
                  maxLength={8000}
                  required
                  disabled={busy}
                />
                <div>
                  <span>
                    引用核验确认来源存在；请结合原文判断推理是否正确。
                  </span>
                  {busy ? (
                    <button
                      type="button"
                      onClick={async () => {
                        await api("/conversations/" + id + "/cancel", {
                          method: "POST",
                        }).catch((e) => setError(e.message));
                      }}
                    >
                      <Square size={15} />
                      停止生成
                    </button>
                  ) : (
                    <button className="primary" disabled={!draft.trim()}>
                      <Send size={15} />
                      发送问题
                    </button>
                  )}
                </div>
              </form>
            </>
          )}
        </section>
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title="新建学习对话">
        <form className="form-stack" onSubmit={create}>
          <label>
            对话标题
            <input
              name="title"
              defaultValue="新的学习对话"
              required
              maxLength={200}
            />
          </label>
          <label>
            课程范围
            <select value={course} onChange={(e) => setCourse(e.target.value)}>
              <option value="">整个知识库</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <fieldset>
            <legend>指定资料（不勾选则检索该范围全部资料）</legend>
            <div className="document-picker">
              {documents.map((d) => (
                <label key={d.id} className="checkbox-label">
                  <input type="checkbox" name="documents" value={d.id} />
                  {d.title}
                </label>
              ))}
            </div>
          </fieldset>
          <button className="primary">创建对话</button>
        </form>
      </Modal>
    </>
  );
}

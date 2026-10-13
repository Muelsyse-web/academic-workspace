import { Link, useNavigate } from "react-router-dom";
import {
  BookOpen,
  Files,
  NotebookPen,
  ArrowRight,
  Search,
  Plus,
  ArrowUpRight,
  Clock3,
} from "lucide-react";
import {
  useData,
  PageHeading,
  ErrorMessage,
  Loading,
  Empty,
} from "../components/Shared";
import { type Course } from "../api";
type Overview = {
  courses: number;
  documents: number;
  notes: number;
  flashcards: number;
  due_cards: number;
  activities: { id: string; description: string; created_at: string }[];
  recent_documents: {
    id: string;
    title: string;
    kind: string;
    status: string;
  }[];
};
export function Dashboard() {
  const { data, error, loading } = useData<Overview>("/dashboard", {
    courses: 0,
    documents: 0,
    notes: 0,
    flashcards: 0,
    due_cards: 0,
    activities: [],
    recent_documents: [],
  });
  const { data: courses } = useData<Course[]>("/courses", []),
    navigate = useNavigate();
  return (
    <>
      <PageHeading
        eyebrow="YOUR LOCAL ACADEMIC WORKSPACE"
        title="今天，学一点新知识。"
        description="让资料有序，让思考相连。这里是你的个人学术空间。"
        action={
          <Link className="primary" to="/library">
            <Plus size={17} />
            导入资料
          </Link>
        }
      />
      <ErrorMessage error={error} />
      <section className="hero">
        <div>
          <span className="eyebrow">A LITTLE CURIOSITY, EVERY DAY</span>
          <h2>从一个好问题开始。</h2>
          <p>检索课程资料，找到原文，再把理解写成自己的笔记。</p>
          <form
            className="hero-search"
            onSubmit={(e) => {
              e.preventDefault();
              const q = new FormData(e.currentTarget).get("q");
              navigate("/search?q=" + encodeURIComponent(String(q)));
            }}
          >
            <Search size={19} />
            <input
              name="q"
              aria-label="全局搜索"
              placeholder="你今天想弄懂什么？"
              required
            />
            <button aria-label="前往搜索" className="icon-button">
              <ArrowRight size={20} />
            </button>
          </form>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="book-shape">
            <BookOpen size={72} strokeWidth={1} />
          </div>
          <span className="art-dot dot-one" />
          <span className="art-dot dot-two" />
          <span className="art-label">Ideas belong together.</span>
        </div>
      </section>
      {loading ? (
        <Loading />
      ) : (
        <div className="stats-grid">
          {[
            [BookOpen, "课程", data.courses],
            [Files, "资料", data.documents],
            [NotebookPen, "笔记", data.notes],
            [Clock3, "待复习卡片", data.due_cards],
          ].map(([Icon, label, value]) => {
            const Glyph = Icon as typeof BookOpen;
            return (
              <div className="stat" key={String(label)}>
                <span className="stat-icon">
                  <Glyph size={20} />
                </span>
                <div>
                  <span>{String(label)}</span>
                  <strong>{String(value)}</strong>
                </div>
              </div>
            );
          })}
        </div>
      )}
      <div className="dashboard-columns">
        <div>
          <div className="section-heading">
            <h2>
              我的课程 <span className="count">{courses.length}</span>
            </h2>
            <Link to="/courses">
              查看全部 <ArrowRight size={15} />
            </Link>
          </div>
          {courses.length ? (
            <div className="course-grid compact">
              {courses.slice(0, 4).map((c) => (
                <Link
                  to={"/library?course=" + c.id}
                  className="course-card"
                  style={{ "--course-color": c.color } as React.CSSProperties}
                  key={c.id}
                >
                  <div className="course-card-top">
                    <span className="course-symbol">
                      <BookOpen size={23} />
                    </span>
                    <ArrowUpRight size={18} />
                  </div>
                  <span className="eyebrow">{c.code || c.semester}</span>
                  <h3>{c.name}</h3>
                  <p>
                    {c.document_count || 0} 份资料 · {c.note_count || 0} 篇笔记
                    · {c.semester}
                  </p>
                  <div className="course-progress">
                    <span>待复习 {c.due_count || 0} 张</span>
                    <span>已作答 {c.answered_count || 0} 题</span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <Empty
              title="你的课程，由你组织"
              description="创建课程，开始整理这一学期的学习资料。"
              action={
                <Link className="button" to="/courses">
                  创建第一门课程
                </Link>
              }
            />
          )}
          <div className="section-heading spaced">
            <h2>最近导入</h2>
            <Link to="/library">
              资料库 <ArrowRight size={15} />
            </Link>
          </div>
          <div className="panel">
            {data.recent_documents.length ? (
              data.recent_documents.map((d) => (
                <Link
                  className="document-row"
                  to={"/documents/" + d.id}
                  key={d.id}
                >
                  <span className={"file-badge " + d.kind}>
                    {d.kind.toUpperCase()}
                  </span>
                  <span className="grow">
                    {d.title}
                    <small>
                      {d.status === "ready" ? "已建立索引" : d.status}
                    </small>
                  </span>
                  <ArrowUpRight size={17} />
                </Link>
              ))
            ) : (
              <p className="panel-message">
                导入后，你最近读过的资料会出现在这里。
              </p>
            )}
          </div>
        </div>
        <aside>
          <div className="section-heading">
            <h2>近期活动</h2>
            <span className="live-dot" />
          </div>
          <div className="panel activity-panel">
            {data.activities.length ? (
              data.activities.slice(0, 8).map((a) => (
                <div className="activity" key={a.id}>
                  <span className="timeline-dot" />
                  <div>
                    <p>{a.description}</p>
                    <time>
                      {new Date(a.created_at).toLocaleString("zh-CN", {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </time>
                  </div>
                </div>
              ))
            ) : (
              <p className="panel-message">
                每一次整理、阅读和复习，都会留下进展。
              </p>
            )}
          </div>
          <div className="local-note">
            <span className="eyebrow">LOCAL BY DESIGN</span>
            <h3>你的知识，留在本地。</h3>
            <p>资料与学习记录保存在这台设备。基础检索不依赖 AI 服务。</p>
          </div>
        </aside>
      </div>
    </>
  );
}

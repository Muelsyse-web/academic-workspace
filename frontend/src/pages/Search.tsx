import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Search as SearchIcon, ArrowUpRight } from "lucide-react";
import {
  api,
  locationLabel,
  type Course,
  type SearchHit,
  type Document,
} from "../api";
import {
  PageHeading,
  ErrorMessage,
  Empty,
  Loading,
  useData,
} from "../components/Shared";
type ResultHit =
  SearchHit | { note_id: string; title: string; text: string; kind: "note" };
export function Search() {
  const [params] = useSearchParams(),
    [query, setQuery] = useState(params.get("q") || ""),
    [course, setCourse] = useState(params.get("course") || ""),
    [kind, setKind] = useState(""),
    [documentId, setDocumentId] = useState(""),
    [tag, setTag] = useState(""),
    [target, setTarget] = useState("documents"),
    [mode, setMode] = useState("keyword"),
    [hint, setHint] = useState("关键词检索 · 无需 AI 模型");
  const [hits, setHits] = useState<ResultHit[]>([]),
    [total, setTotal] = useState(0),
    [searched, setSearched] = useState(false),
    [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const { data: courses } = useData<Course[]>("/courses", []);
  const { data: documents } = useData<Document[]>(
    "/documents?course_id=" + course,
    [],
  );
  function resetResults() {
    setHits([]);
    setTotal(0);
    setSearched(false);
  }
  async function search(event?: FormEvent, offset = 0) {
    event?.preventDefault();
    setLoading(true);
    setError("");
    try {
      let result: {
        hits: ResultHit[];
        total: number;
        mode?: string;
        warning?: string;
        candidate_limit?: number;
      };
      if (target === "notes") {
        const filters = new URLSearchParams({ q: query });
        if (course) filters.set("course_id", course);
        const notes = await api<{ id: string; title: string; body: string }[]>(
          "/notes?" + filters,
        );
        result = {
          mode: "notes",
          total: notes.length,
          hits: notes.slice(offset, offset + 20).map((note) => {
            const at = Math.max(
              0,
              note.body.toLowerCase().indexOf(query.toLowerCase()) - 100,
            );
            return {
              note_id: note.id,
              title: note.title,
              text: note.body.slice(at, at + 500),
              kind: "note",
            };
          }),
        };
      } else
        result = await api<{
          hits: SearchHit[];
          total: number;
          mode: string;
          warning?: string;
          candidate_limit?: number;
        }>(
          "/search?" +
            new URLSearchParams({
              q: query,
              course_id: course,
              document_id: documentId,
              tag,
              kind,
              mode,
              offset: String(offset),
            }),
        );
      setHint(
        result.warning ||
          (result.mode === "hybrid"
            ? "混合检索 · 最多 200 个候选片段"
            : result.mode === "semantic"
              ? "语义检索 · 本地 Embedding"
              : result.mode === "notes"
                ? "笔记全文检索"
                : "关键词检索 · 无需 AI 模型"),
      );
      setHits(
        offset ? (previous) => [...previous, ...result.hits] : result.hits,
      );
      setTotal(result.total);
      setSearched(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="FIND YOUR NEXT CONNECTION"
        title="搜索知识"
        description="从一个概念出发，回到它在课程资料中的原始位置。"
      />
      <form className="search-panel" onSubmit={search}>
        <div className="search-input">
          <SearchIcon size={21} />
          <input
            type="search"
            aria-label="搜索知识"
            placeholder="搜索概念、公式或中英文关键词…"
            value={query}
            disabled={loading}
            onChange={(e) => {
              setQuery(e.target.value);
              resetResults();
            }}
            required
          />
          <button className="primary" disabled={loading}>
            搜索
          </button>
        </div>
        <div className="filters">
          <select
            aria-label="搜索内容类型"
            value={target}
            disabled={loading}
            onChange={(e) => {
              setTarget(e.target.value);
              resetResults();
            }}
          >
            <option value="documents">资料内容</option>
            <option value="notes">学习笔记</option>
          </select>
          <select
            aria-label="检索方式"
            value={mode}
            disabled={loading || target === "notes"}
            onChange={(e) => {
              setMode(e.target.value);
              resetResults();
            }}
          >
            <option value="keyword">关键词</option>
            <option value="semantic">语义</option>
            <option value="hybrid">混合</option>
          </select>
          <select
            aria-label="搜索课程"
            value={course}
            disabled={loading}
            onChange={(e) => {
              setCourse(e.target.value);
              setDocumentId("");
              resetResults();
            }}
          >
            <option value="">全部课程</option>
            {courses.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <select
            aria-label="文件类型"
            value={kind}
            disabled={loading}
            onChange={(e) => {
              setKind(e.target.value);
              resetResults();
            }}
          >
            <option value="">全部格式</option>
            {["pdf", "pptx", "docx", "md", "txt"].map((k) => (
              <option key={k} value={k}>
                {k.toUpperCase()}
              </option>
            ))}
          </select>
          <select
            aria-label="指定文件"
            disabled={loading || target === "notes"}
            value={documentId}
            onChange={(e) => {
              setDocumentId(e.target.value);
              resetResults();
            }}
          >
            <option value="">全部文件</option>
            {documents.map((d) => (
              <option key={d.id} value={d.id}>
                [{d.kind.toUpperCase()}] {d.title} · {d.filename}
              </option>
            ))}
          </select>
          <input
            aria-label="搜索标签"
            placeholder="标签（可选）"
            disabled={loading || target === "notes"}
            value={tag}
            onChange={(e) => {
              setTag(e.target.value);
              resetResults();
            }}
          />
          <span className="subtle">{hint}</span>
        </div>
      </form>
      <ErrorMessage error={error} />
      {loading && !hits.length ? (
        <Loading />
      ) : searched ? (
        <>
          <div className="section-heading">
            <h2>搜索结果</h2>
            <span>{total} 个匹配片段</span>
          </div>
          {hits.length ? (
            <div className="search-results">
              {hits.map((hit) => (
                <article
                  className="search-result"
                  key={"note_id" in hit ? hit.note_id : hit.chunk_id}
                >
                  <div className="result-meta">
                    <span className={"file-badge " + hit.kind}>
                      {hit.kind.toUpperCase()}
                    </span>
                    <span>
                      {"note_id" in hit
                        ? "学习笔记"
                        : locationLabel(hit.locator_type, hit.locator)}
                    </span>
                  </div>
                  <Link
                    to={
                      "note_id" in hit
                        ? `/notes?id=${hit.note_id}`
                        : `/documents/${hit.document_id}?version=${hit.version_id}&locator=${hit.locator}`
                    }
                  >
                    <h3>{hit.title}</h3>
                    <ArrowUpRight size={18} />
                  </Link>
                  <p>{hit.text}</p>
                </article>
              ))}
            </div>
          ) : (
            <Empty
              title="没有找到匹配内容"
              description="试试更短的关键词，或调整课程和格式筛选。"
            />
          )}
          {hits.length < total && (
            <button
              disabled={loading}
              onClick={() => search(undefined, hits.length)}
            >
              加载更多
            </button>
          )}
        </>
      ) : (
        <Empty
          title="知识就在你的资料里"
          description="例如搜索 gradient descent、梯度下降或 Bayes。点击结果即可查看原文。"
        />
      )}
    </>
  );
}

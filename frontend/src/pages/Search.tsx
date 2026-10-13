import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Search as SearchIcon, ArrowUpRight } from "lucide-react";
import { api, locationLabel, type Course, type SearchHit } from "../api";
import {
  PageHeading,
  ErrorMessage,
  Empty,
  Loading,
  useData,
} from "../components/Shared";
export function Search() {
  const [params] = useSearchParams(),
    [query, setQuery] = useState(params.get("q") || ""),
    [course, setCourse] = useState(params.get("course") || ""),
    [kind, setKind] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]),
    [total, setTotal] = useState(0),
    [searched, setSearched] = useState(false),
    [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const { data: courses } = useData<Course[]>("/courses", []);
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
      const result = await api<{ hits: SearchHit[]; total: number }>(
        "/search?" +
          new URLSearchParams({
            q: query,
            course_id: course,
            kind,
            offset: String(offset),
          }),
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
            aria-label="搜索课程"
            value={course}
            disabled={loading}
            onChange={(e) => {
              setCourse(e.target.value);
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
          <span className="subtle">关键词检索 · 无需 AI 模型</span>
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
                <article className="search-result" key={hit.chunk_id}>
                  <div className="result-meta">
                    <span className={"file-badge " + hit.kind}>
                      {hit.kind.toUpperCase()}
                    </span>
                    <span>{locationLabel(hit.locator_type, hit.locator)}</span>
                  </div>
                  <Link
                    to={`/documents/${hit.document_id}?version=${hit.version_id}&locator=${hit.locator}`}
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

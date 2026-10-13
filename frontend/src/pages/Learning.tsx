import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  Plus,
  Layers,
  ClipboardList,
  Sparkles,
  Pencil,
  Trash2,
  RotateCcw,
  Check,
} from "lucide-react";
import { api, type Course } from "../api";
import {
  useData,
  PageHeading,
  ErrorMessage,
  Empty,
  Modal,
} from "../components/Shared";
import { Markdown } from "../components/Markdown";
import { CardEditor } from "../components/study/CardEditor";
import { QuizEditor } from "../components/study/QuizEditor";
import { QuizRunner } from "../components/study/QuizRunner";
import { SourceLinks } from "../components/study/SourceLinks";
import { Generate, type Generated } from "../components/study/Generate";
import {
  blankQuestion,
  type Card,
  type Quiz,
  type Attempt,
  type SourceRef,
} from "../components/study/types";
export function Learning() {
  const [tab, setTab] = useState("cards"),
    [course, setCourse] = useState(""),
    [revision, setRevision] = useState(0),
    [error, setError] = useState(""),
    [editingCard, setEditingCard] = useState<Card | null>(null),
    [editingQuiz, setEditingQuiz] = useState<Quiz | null>(null),
    [reviewing, setReviewing] = useState<Card | null>(null),
    [revealed, setRevealed] = useState(false),
    [busy, setBusy] = useState(false),
    [quiz, setQuiz] = useState<Quiz | null>(null),
    [generator, setGenerator] = useState(false),
    [focus, setFocus] = useState(""),
    [drafts, setDrafts] = useState<Card[]>([]),
    [draftIndex, setDraftIndex] = useState<number | null>(null),
    [summary, setSummary] = useState<{
      answer: string;
      sources: SourceRef[];
    } | null>(null),
    [notice, setNotice] = useState("");
  const reviewKey = useRef(crypto.randomUUID());
  const suffix = course ? "?course_id=" + course : "";
  const { data: cards } = useData<Card[]>("/flashcards" + suffix, [], revision),
    { data: quizzes } = useData<Quiz[]>("/quizzes" + suffix, [], revision),
    { data: courses } = useData<Course[]>("/courses", []),
    { data: attempts } = useData<Attempt[]>("/attempts" + suffix, [], revision),
    { data: weak } = useData<
      {
        course_id: string;
        topic: string;
        incorrect_count: number;
        total_count: number;
      }[]
    >("/learning/weak-topics" + suffix, [], revision),
    { data: wrong } = useData<
      { question: Quiz["questions"][number]; created_at: string }[]
    >("/learning/wrong-questions" + suffix, [], revision),
    { data: reviews } = useData<
      {
        id: string;
        rating: string;
        due_at: string;
        reviewed_at: string;
        topic: string;
      }[]
    >("/reviews" + suffix, [], revision);
  const due = cards.filter((c) => Date.parse(c.due_at || "") <= Date.now());
  function refresh() {
    setRevision((v) => v + 1);
  }
  function review(card: Card) {
    setReviewing(card);
    setRevealed(false);
    reviewKey.current = crypto.randomUUID();
  }
  async function rate(rating: string) {
    if (!reviewing) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ due_at: string }>(
        "/flashcards/" + reviewing.id + "/review",
        {
          method: "POST",
          body: JSON.stringify({ rating, idempotency_key: reviewKey.current }),
        },
      );
      setNotice(
        "已记录复习，下次到期：" +
          new Date(result.due_at).toLocaleString("zh-CN", {
            timeZone: "Asia/Shanghai",
          }),
      );
      setReviewing(null);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove(kind: string, id: string) {
    if (!confirm("删除此学习条目？历史记录会保留。")) return;
    try {
      await api("/" + kind + "/" + id, { method: "DELETE" });
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function generated(data: Generated) {
    setGenerator(false);
    if (data.kind === "flashcards") {
      setDrafts(data.drafts);
      setTab("cards");
    }
    if (data.kind === "quiz") setEditingQuiz(data.draft);
    if (data.kind === "summary") setSummary(data);
  }
  return (
    <>
      <PageHeading
        eyebrow="SMALL STEPS, LASTING KNOWLEDGE"
        title="练习与复习"
        description="用主动回忆巩固理解。手工学习始终可用，AI 可以帮助你准备草稿。"
        action={
          <button
            onClick={() => {
              setFocus("");
              setGenerator(true);
            }}
          >
            <Sparkles size={16} />
            AI 学习草稿
          </button>
        }
      />
      <ErrorMessage error={error} />
      {notice && (
        <div className="notice" role="status">
          {notice}
        </div>
      )}
      <div className="learning-top">
        <div className="tab-bar" role="tablist" aria-label="学习方式">
          {[
            ["cards", "Flashcards"],
            ["quizzes", "Quiz 练习"],
            ["history", "进度与错题"],
          ].map(([value, label]) => (
            <button
              role="tab"
              aria-selected={tab === value}
              key={value}
              className={tab === value ? "active" : ""}
              onClick={() => {
                setTab(value);
                setQuiz(null);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <select
          aria-label="学习课程"
          value={course}
          onChange={(e) => {
            setCourse(e.target.value);
            setQuiz(null);
          }}
        >
          <option value="">全部课程</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
      {tab === "cards" && (
        <>
          <div className="review-banner">
            <div>
              <span className="eyebrow">SPACED REPETITION · SM-2</span>
              <h2>{due.length} 张卡片等待复习</h2>
              <p>先尝试回忆，再翻开答案。每次评分会安排下一次复习。</p>
            </div>
            <div className="button-group">
              <button
                className="primary"
                disabled={!due.length}
                onClick={() => review(due[0])}
              >
                <RotateCcw size={16} />
                开始到期复习
              </button>
              <button
                onClick={() => {
                  setDraftIndex(null);
                  setEditingCard({
                    front: "",
                    back: "",
                    course_id: course || null,
                    topic: "",
                    sources: [],
                  });
                }}
              >
                <Plus size={16} />
                新建卡片
              </button>
            </div>
          </div>
          {drafts.length > 0 && (
            <section className="draft-panel">
              <h3>AI 草稿 · 尚未保存</h3>
              {drafts.map((card, index) => (
                <div className="draft-row" key={index}>
                  <span>{card.front}</span>
                  <button
                    onClick={() => {
                      setDraftIndex(index);
                      setEditingCard(card);
                    }}
                  >
                    核对并保存
                  </button>
                  <button
                    onClick={() =>
                      setDrafts((all) => all.filter((_, i) => i !== index))
                    }
                  >
                    丢弃
                  </button>
                </div>
              ))}
            </section>
          )}
          {cards.length ? (
            <div className="flashcard-grid">
              {cards.map((card) => (
                <article className="flashcard-tile" key={card.id}>
                  <div className="section-heading">
                    <span className="pill">{card.topic || "未设主题"}</span>
                    <Layers size={17} />
                  </div>
                  <Markdown text={card.front} />
                  <small>
                    下次复习{" "}
                    {new Date(card.due_at!).toLocaleDateString("zh-CN", {
                      timeZone: "Asia/Shanghai",
                    })}
                  </small>
                  <div className="course-card-footer">
                    <button
                      className="text-button"
                      onClick={() => review(card)}
                    >
                      翻卡复习 →
                    </button>
                    <div>
                      <button
                        className="icon-button"
                        aria-label={"编辑卡片 " + card.front}
                        onClick={() => {
                          setDraftIndex(null);
                          setEditingCard(card);
                        }}
                      >
                        <Pencil size={15} />
                      </button>
                      <button
                        className="icon-button"
                        aria-label={"删除卡片 " + card.front}
                        onClick={() => remove("flashcards", card.id!)}
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <Empty
              title="把知识点变成一张卡片"
              description="手工写下问题与答案，或根据课程资料生成有来源的草稿。"
            />
          )}
        </>
      )}
      {tab === "quizzes" &&
        (quiz ? (
          <QuizRunner
            key={quiz.id}
            quiz={quiz}
            onClose={() => setQuiz(null)}
            onComplete={refresh}
          />
        ) : (
          <>
            <div className="section-heading">
              <h2>
                练习集 <span className="count">{quizzes.length}</span>
              </h2>
              <button
                className="primary"
                onClick={() =>
                  setEditingQuiz({
                    title: "",
                    course_id: course || null,
                    questions: [blankQuestion()],
                  })
                }
              >
                <Plus size={16} />
                新建练习
              </button>
            </div>
            {quizzes.length ? (
              <div className="course-grid">
                {quizzes.map((q) => (
                  <article className="course-card" key={q.id}>
                    <div className="course-card-top">
                      <ClipboardList size={25} />
                      <span className="pill">{q.questions.length} 道题</span>
                    </div>
                    <h3>{q.title}</h3>
                    <div className="course-card-footer">
                      <button
                        className="text-button"
                        onClick={() => setQuiz(q)}
                      >
                        开始作答 →
                      </button>
                      <div>
                        <button
                          className="icon-button"
                          aria-label={"编辑练习 " + q.title}
                          onClick={() => setEditingQuiz(q)}
                        >
                          <Pencil size={15} />
                        </button>
                        <button
                          className="icon-button"
                          aria-label={"删除练习 " + q.title}
                          onClick={() => remove("quizzes", q.id!)}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <Empty
                title="用一道题检验理解"
                description="支持单选、多选、简答和数学题。简答与推导根据参考答案进行自评。"
              />
            )}
          </>
        ))}
      {tab === "history" && (
        <div className="learning-history">
          <section>
            <h2>薄弱知识点</h2>
            {weak.length ? (
              weak.map((item, index) => (
                <div className="weak-row" key={index}>
                  <div>
                    <strong>{item.topic || "未分类知识点"}</strong>
                    <small>
                      {item.incorrect_count} 次需巩固 / {item.total_count}{" "}
                      次作答
                    </small>
                  </div>
                  <button
                    onClick={() => {
                      setFocus(item.topic);
                      setCourse(item.course_id || "");
                      setGenerator(true);
                    }}
                  >
                    针对性生成练习
                  </button>
                </div>
              ))
            ) : (
              <p className="panel-message">
                完成练习后，这里会显示需要巩固的主题。
              </p>
            )}
            <h2>答题记录</h2>
            {attempts.map((attempt) => (
              <details className="history-item" key={attempt.id}>
                <summary>
                  {attempt.quiz_title}{" "}
                  <strong>
                    {attempt.score}/{attempt.total}
                  </strong>{" "}
                  <small>
                    {new Date(attempt.created_at).toLocaleDateString("zh-CN", {
                      timeZone: "Asia/Shanghai",
                    })}
                  </small>
                </summary>
                {attempt.answers.map((answer, index) => (
                  <div className="question-feedback" key={index}>
                    <Markdown text={answer.question.prompt} />
                    <p>
                      {answer.correct ? "正确" : "需巩固"} ·{" "}
                      {answer.question.options.length
                        ? answer.selected
                            .map((i) => answer.question.options[i])
                            .join("；")
                        : answer.text}
                    </p>
                  </div>
                ))}
              </details>
            ))}
            <h2>复习记录</h2>
            {reviews.slice(0, 30).map((r) => (
              <p key={r.id} className="review-history-row">
                {r.topic || "Flashcard"} · {r.rating} ·{" "}
                {new Date(r.reviewed_at).toLocaleString("zh-CN", {
                  timeZone: "Asia/Shanghai",
                })}
              </p>
            ))}
          </section>
          <section>
            <h2>错题回顾</h2>
            {wrong.map((item, index) => (
              <article className="question-card" key={index}>
                <span className="pill">{item.question.topic || "未分类"}</span>
                <Markdown text={item.question.prompt} />
                <details>
                  <summary>参考答案与解析</summary>
                  <Markdown
                    text={
                      item.question.answer ||
                      item.question.correct_indices
                        .map((i) => item.question.options[i])
                        .join("\n\n")
                    }
                  />
                  <Markdown text={item.question.explanation} />
                  <SourceLinks sources={item.question.sources} />
                </details>
              </article>
            ))}
            {!wrong.length && (
              <p className="panel-message">暂时没有错题记录。</p>
            )}
          </section>
        </div>
      )}
      {editingCard && (
        <CardEditor
          initial={editingCard}
          courses={courses}
          onClose={() => setEditingCard(null)}
          onSaved={() => {
            setEditingCard(null);
            if (draftIndex !== null)
              setDrafts((all) => all.filter((_, i) => i !== draftIndex));
            setDraftIndex(null);
            refresh();
          }}
        />
      )}
      {editingQuiz && (
        <QuizEditor
          initial={editingQuiz}
          courses={courses}
          onClose={() => setEditingQuiz(null)}
          onSaved={() => {
            setEditingQuiz(null);
            setTab("quizzes");
            refresh();
          }}
        />
      )}
      {reviewing && (
        <Modal
          open
          onClose={() => !busy && setReviewing(null)}
          title="主动回忆"
        >
          <div className="review-card">
            <span className="eyebrow">
              {revealed ? "参考答案" : "先尝试回忆"}
            </span>
            <Markdown text={reviewing.front} />
            {revealed ? (
              <>
                <div className="review-answer">
                  <Markdown text={reviewing.back} />
                </div>
                <SourceLinks sources={reviewing.sources} />
                <div className="rating-buttons">
                  {[
                    ["again", "再来一次"],
                    ["hard", "困难"],
                    ["good", "记得"],
                    ["easy", "轻松"],
                  ].map(([rating, label]) => (
                    <button
                      disabled={busy}
                      key={rating}
                      onClick={() => rate(rating)}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <button className="primary" onClick={() => setRevealed(true)}>
                显示答案
              </button>
            )}
          </div>
        </Modal>
      )}
      {generator && (
        <Generate
          courses={courses}
          course={course}
          focus={focus}
          onClose={() => setGenerator(false)}
          onGenerated={generated}
        />
      )}{" "}
      {summary && (
        <Modal open onClose={() => setSummary(null)} title="知识总结与复习建议">
          <Markdown text={summary.answer} />
          <SourceLinks sources={summary.sources} />
          <button
            className="primary"
            onClick={async () => {
              try {
                const sources = summary.sources.map(
                  ({
                    document_id,
                    version_id,
                    locator_type,
                    locator,
                    quote,
                  }) => ({
                    document_id,
                    version_id,
                    locator_type,
                    locator,
                    quote,
                  }),
                );
                await api("/notes", {
                  method: "POST",
                  body: JSON.stringify({
                    title: focus ? focus + " · 学习总结" : "课程学习总结",
                    body: summary.answer,
                    course_id: course || null,
                    sources,
                  }),
                });
                setSummary(null);
                setNotice("总结已保存到学习笔记。");
              } catch (e) {
                setError((e as Error).message);
              }
            }}
          >
            <Check size={16} />
            保存为笔记
          </button>
        </Modal>
      )}
    </>
  );
}

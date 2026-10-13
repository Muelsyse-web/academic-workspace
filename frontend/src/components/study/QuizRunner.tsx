import { useState, type FormEvent } from "react";
import { api } from "../../api";
import { ErrorMessage } from "../Shared";
import { Markdown } from "../Markdown";
import { SourceLinks } from "./SourceLinks";
import { kindLabels, type Quiz, type Answer, type Attempt } from "./types";
export function QuizRunner({
  quiz,
  onClose,
  onComplete,
}: {
  quiz: Quiz;
  onClose: () => void;
  onComplete: () => void;
}) {
  const [answers, setAnswers] = useState<Answer[]>(() =>
      quiz.questions.map((q) => ({
        question_id: q.id!,
        selected: [],
        text: "",
        self_correct: null,
      })),
    ),
    [revealed, setRevealed] = useState<string[]>([]),
    [result, setResult] = useState<Attempt | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [key] = useState(() => crypto.randomUUID());
  function update(index: number, value: Partial<Answer>) {
    setAnswers((all) =>
      all.map((a, i) => (i === index ? { ...a, ...value } : a)),
    );
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const attempt = await api<Attempt>("/quizzes/" + quiz.id + "/attempts", {
        method: "POST",
        body: JSON.stringify({ answers, idempotency_key: key }),
      });
      setResult(attempt);
      onComplete();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="quiz-runner">
      <div className="section-heading">
        <div>
          <span className="eyebrow">PRACTICE SESSION</span>
          <h2>{quiz.title}</h2>
        </div>
        <button onClick={onClose}>{result ? "完成" : "返回练习列表"}</button>
      </div>
      {result && (
        <div className="notice" role="status">
          本次得分 {result.score} / {result.total}
          。选择题按答案判分；简答和数学题记录你的自评。
        </div>
      )}
      <form onSubmit={submit}>
        <div className="question-list">
          {quiz.questions.map((q, index) => (
            <article key={q.id} className="question-card">
              <span className="eyebrow">
                {index + 1} / {quiz.questions.length} · {kindLabels[q.kind]}
              </span>
              <Markdown text={q.prompt} />
              {["single", "multiple"].includes(q.kind) ? (
                <fieldset disabled={Boolean(result) || busy}>
                  {q.options.map((option, i) => (
                    <label key={i} className="answer-option">
                      <input
                        type={q.kind === "single" ? "radio" : "checkbox"}
                        name={"answer-" + q.id}
                        checked={answers[index].selected.includes(i)}
                        onChange={(e) =>
                          update(index, {
                            selected:
                              q.kind === "single"
                                ? [i]
                                : e.target.checked
                                  ? [...answers[index].selected, i]
                                  : answers[index].selected.filter(
                                      (n) => n !== i,
                                    ),
                          })
                        }
                      />
                      <span>{String.fromCharCode(65 + i)}.</span>
                      <Markdown text={option} />
                    </label>
                  ))}
                </fieldset>
              ) : (
                <>
                  <textarea
                    aria-label={"第 " + (index + 1) + " 题作答"}
                    placeholder="写下你的答案或推导过程…"
                    required
                    value={answers[index].text}
                    disabled={Boolean(result) || busy}
                    onChange={(e) => update(index, { text: e.target.value })}
                  />
                  {revealed.includes(q.id!) || result ? (
                    <div className="self-grade">
                      <span className="eyebrow">参考答案 · 请自行核对</span>
                      <Markdown text={q.answer} />
                      <div className="button-group">
                        <button
                          type="button"
                          disabled={Boolean(result)}
                          className={
                            answers[index].self_correct === true
                              ? "primary"
                              : ""
                          }
                          onClick={() => update(index, { self_correct: true })}
                        >
                          我答对了
                        </button>
                        <button
                          type="button"
                          disabled={Boolean(result)}
                          className={
                            answers[index].self_correct === false
                              ? "primary"
                              : ""
                          }
                          onClick={() => update(index, { self_correct: false })}
                        >
                          需要再练
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setRevealed([...revealed, q.id!])}
                    >
                      查看参考答案并自评
                    </button>
                  )}
                </>
              )}
              {result && (
                <div
                  className={
                    "question-feedback " +
                    (result.answers[index].correct ? "correct" : "incorrect")
                  }
                >
                  <strong>
                    {result.answers[index].correct
                      ? "回答正确"
                      : "加入错题记录"}
                  </strong>
                  {q.correct_indices.length > 0 && (
                    <p>
                      参考选项：
                      {q.correct_indices
                        .map((n) => String.fromCharCode(65 + n))
                        .join("、")}
                    </p>
                  )}
                  <Markdown text={q.explanation} />
                  <SourceLinks sources={q.sources} />
                </div>
              )}
            </article>
          ))}
        </div>
        <ErrorMessage error={error} />
        {!result && (
          <button className="primary" disabled={busy}>
            {busy ? "记录中…" : "提交答题"}
          </button>
        )}
      </form>
    </section>
  );
}

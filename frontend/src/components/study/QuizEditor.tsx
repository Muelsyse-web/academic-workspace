import { useState, type FormEvent } from "react";
import { Plus, Trash2 } from "lucide-react";
import { api, type Course } from "../../api";
import { Modal, ErrorMessage } from "../Shared";
import { blankQuestion, kindLabels, type Quiz, type Question } from "./types";
export function QuizEditor({
  initial,
  courses,
  onClose,
  onSaved,
}: {
  initial: Quiz;
  courses: Course[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [quiz, setQuiz] = useState(initial),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  function update(index: number, value: Partial<Question>) {
    setQuiz((q) => ({
      ...q,
      questions: q.questions.map((question, i) =>
        i === index ? { ...question, ...value } : question,
      ),
    }));
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(quiz.id ? "/quizzes/" + quiz.id : "/quizzes", {
        method: quiz.id ? "PATCH" : "POST",
        body: JSON.stringify({
          title: quiz.title,
          course_id: quiz.course_id,
          questions: quiz.questions.map(({ id, ...q }) => q),
        }),
      });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open onClose={onClose} title={quiz.id ? "编辑练习" : "新建练习"}>
      <form className="form-stack" onSubmit={save}>
        <label>
          练习标题
          <input
            required
            value={quiz.title}
            onChange={(e) => setQuiz({ ...quiz, title: e.target.value })}
          />
        </label>
        <label>
          练习课程
          <select
            value={quiz.course_id || ""}
            onChange={(e) =>
              setQuiz({ ...quiz, course_id: e.target.value || null })
            }
          >
            <option value="">不限定课程</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        {quiz.questions.map((q, index) => (
          <section className="question-editor" key={index}>
            <div className="section-heading">
              <h3>第 {index + 1} 题</h3>
              {quiz.questions.length > 1 && (
                <button
                  type="button"
                  className="icon-button"
                  aria-label={"删除第 " + (index + 1) + " 题"}
                  onClick={() =>
                    setQuiz({
                      ...quiz,
                      questions: quiz.questions.filter((_, i) => i !== index),
                    })
                  }
                >
                  <Trash2 size={15} />
                </button>
              )}
            </div>
            <label>
              题型
              <select
                aria-label={"第 " + (index + 1) + " 题题型"}
                value={q.kind}
                onChange={(e) => {
                  const kind = e.target.value as Question["kind"];
                  update(index, {
                    kind,
                    options: ["single", "multiple"].includes(kind)
                      ? ["", ""]
                      : [],
                    correct_indices: ["single", "multiple"].includes(kind)
                      ? [0]
                      : [],
                  });
                }}
              >
                {Object.entries(kindLabels).map(([k, label]) => (
                  <option value={k} key={k}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              题干
              <textarea
                aria-label={"第 " + (index + 1) + " 题题干"}
                required
                value={q.prompt}
                onChange={(e) => update(index, { prompt: e.target.value })}
              />
            </label>
            {["single", "multiple"].includes(q.kind) ? (
              <>
                <label>
                  选项（每行一个）
                  <textarea
                    aria-label={"第 " + (index + 1) + " 题选项"}
                    value={q.options.join("\n")}
                    onChange={(e) => {
                      const options = e.target.value.split("\n");
                      update(index, {
                        options,
                        correct_indices: q.correct_indices.filter(
                          (n) => n < options.length,
                        ),
                      });
                    }}
                  />
                </label>
                <fieldset>
                  <legend>正确选项</legend>
                  {q.options.map((option, i) => (
                    <label key={i} className="checkbox-label">
                      <input
                        type={q.kind === "single" ? "radio" : "checkbox"}
                        name={"correct-" + index}
                        checked={q.correct_indices.includes(i)}
                        onChange={(e) =>
                          update(index, {
                            correct_indices:
                              q.kind === "single"
                                ? [i]
                                : e.target.checked
                                  ? [...q.correct_indices, i]
                                  : q.correct_indices.filter((n) => n !== i),
                          })
                        }
                      />
                      {String.fromCharCode(65 + i)} · {option || "尚未填写"}
                    </label>
                  ))}
                </fieldset>
              </>
            ) : (
              <label>
                参考答案
                <textarea
                  required
                  value={q.answer}
                  onChange={(e) => update(index, { answer: e.target.value })}
                />
              </label>
            )}
            <label>
              解析
              <textarea
                value={q.explanation}
                onChange={(e) => update(index, { explanation: e.target.value })}
              />
            </label>
            <label>
              知识主题
              <input
                value={q.topic}
                onChange={(e) => update(index, { topic: e.target.value })}
              />
            </label>
            {q.sources.length > 0 && (
              <small>已关联 {q.sources.length} 条可追溯来源</small>
            )}
          </section>
        ))}
        <button
          type="button"
          onClick={() =>
            setQuiz({
              ...quiz,
              questions: [...quiz.questions, blankQuestion()],
            })
          }
        >
          <Plus size={15} />
          添加题目
        </button>
        <ErrorMessage error={error} />
        <button className="primary" disabled={busy}>
          保存练习
        </button>
      </form>
    </Modal>
  );
}

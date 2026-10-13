import { useState, type FormEvent } from "react";
import { api, type Course } from "../../api";
import { Modal, ErrorMessage } from "../Shared";
import { Markdown } from "../Markdown";
import type { Card } from "./types";
export function CardEditor({
  initial,
  courses,
  onClose,
  onSaved,
}: {
  initial: Card;
  courses: Course[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [card, setCard] = useState(initial),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const { id, due_at, interval_days, ...data } = card;
      await api(id ? "/flashcards/" + id : "/flashcards", {
        method: id ? "PATCH" : "POST",
        body: JSON.stringify({
          front: data.front,
          back: data.back,
          course_id: data.course_id,
          topic: data.topic,
          sources: data.sources,
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
    <Modal
      open
      onClose={onClose}
      title={card.id ? "编辑卡片" : "新建 Flashcard"}
    >
      <form className="form-stack" onSubmit={save}>
        <label>
          卡片正面
          <textarea
            aria-label="卡片正面"
            required
            value={card.front}
            onChange={(e) => setCard({ ...card, front: e.target.value })}
          />
        </label>
        <label>
          卡片背面
          <textarea
            aria-label="卡片背面"
            required
            value={card.back}
            onChange={(e) => setCard({ ...card, back: e.target.value })}
          />
        </label>
        <div className="form-row">
          <label>
            卡片课程
            <select
              value={card.course_id || ""}
              onChange={(e) =>
                setCard({ ...card, course_id: e.target.value || null })
              }
            >
              <option value="">无课程</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            知识主题
            <input
              value={card.topic}
              onChange={(e) => setCard({ ...card, topic: e.target.value })}
            />
          </label>
        </div>
        {card.sources.length > 0 && (
          <p className="subtle">
            保留 {card.sources.length} 条经过来源校验的引用。
          </p>
        )}
        <details>
          <summary>预览</summary>
          <Markdown text={card.front + "\n\n---\n\n" + card.back} />
        </details>
        <ErrorMessage error={error} />
        <button className="primary" disabled={busy}>
          保存卡片
        </button>
      </form>
    </Modal>
  );
}

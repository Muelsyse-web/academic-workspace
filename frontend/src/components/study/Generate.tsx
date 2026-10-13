import { useState, type FormEvent } from "react";
import { api, type Course, type Document } from "../../api";
import { Modal, ErrorMessage, useData } from "../Shared";
import { kindLabels, type Card, type Quiz, type SourceRef } from "./types";
export type Generated =
  | { kind: "flashcards"; drafts: Card[] }
  | { kind: "quiz"; draft: Quiz }
  | { kind: "summary"; answer: string; sources: SourceRef[] };
export function Generate({
  courses,
  course,
  focus,
  onClose,
  onGenerated,
}: {
  courses: Course[];
  course: string;
  focus: string;
  onClose: () => void;
  onGenerated: (data: Generated) => void;
}) {
  const [selectedCourse, setSelectedCourse] = useState(course),
    [kind, setKind] = useState("flashcards"),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const { data: documents } = useData<Document[]>(
    "/documents?course_id=" + selectedCourse,
    [],
  );
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const f = new FormData(event.currentTarget);
    try {
      const data = await api<Generated>("/learning/generate", {
        method: "POST",
        body: JSON.stringify({
          kind,
          course_id: selectedCourse || null,
          document_ids: f.getAll("documents"),
          focus: f.get("focus"),
          count: Number(f.get("count") || 3),
          question_kinds:
            kind === "quiz"
              ? f.getAll("question_kinds")
              : ["single", "multiple", "short", "math"],
        }),
      });
      onGenerated(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal open onClose={() => !busy && onClose()} title="根据资料生成学习草稿">
      <form className="form-stack" onSubmit={submit}>
        <label>
          生成内容
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="flashcards">Flashcards</option>
            <option value="quiz">Quiz 练习题</option>
            <option value="summary">知识总结与复习建议</option>
          </select>
        </label>
        <label>
          资料课程
          <select
            value={selectedCourse}
            onChange={(e) => setSelectedCourse(e.target.value)}
          >
            <option value="">全部课程</option>
            {courses.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          知识主题或复习重点
          <input
            name="focus"
            defaultValue={focus}
            placeholder="例如 gradient descent，或某个薄弱知识点"
          />
        </label>
        <fieldset>
          <legend>指定资料（可选）</legend>
          <div className="document-picker">
            {documents.map((d) => (
              <label className="checkbox-label" key={d.id}>
                <input type="checkbox" name="documents" value={d.id} />
                {d.title}
              </label>
            ))}
          </div>
        </fieldset>
        {kind !== "summary" && (
          <label>
            数量
            <input
              type="number"
              name="count"
              defaultValue={3}
              min={1}
              max={10}
            />
          </label>
        )}
        {kind === "quiz" && (
          <fieldset>
            <legend>题型</legend>
            {Object.entries(kindLabels).map(([k, label]) => (
              <label className="checkbox-label" key={k}>
                <input
                  type="checkbox"
                  name="question_kinds"
                  value={k}
                  defaultChecked
                />
                {label}
              </label>
            ))}
          </fieldset>
        )}
        <p className="subtle">
          需要已启动的本地模型。草稿会验证实际来源，确认并保存后才进入复习库。
        </p>
        <ErrorMessage error={error} />
        <button className="primary" disabled={busy}>
          {busy ? "本地模型正在生成…" : "生成草稿"}
        </button>
      </form>
    </Modal>
  );
}

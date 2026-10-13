import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Plus, ArrowUpRight, BookOpen, Pencil, Trash2 } from "lucide-react";
import { api, post, type Course } from "../api";
import {
  useData,
  PageHeading,
  Modal,
  ErrorMessage,
  Empty,
  Loading,
} from "../components/Shared";
export function Courses() {
  const [revision, setRevision] = useState(0),
    [open, setOpen] = useState(false),
    [semester, setSemester] = useState(""),
    [editing, setEditing] = useState<Course | null>(null);
  const {
    data: courses,
    error,
    loading,
  } = useData<Course[]>("/courses", [], revision);
  const [failure, setFailure] = useState(""),
    [busy, setBusy] = useState(false);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setFailure("");
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try {
      if (editing)
        await api("/courses/" + editing.id, {
          method: "PATCH",
          body: JSON.stringify(values),
        });
      else await post("/courses", values);
      setOpen(false);
      setRevision((v) => v + 1);
    } catch (e) {
      setFailure((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove(course: Course) {
    if (!confirm(`删除课程“${course.name}”？资料原件仍会保留。`)) return;
    try {
      await api("/courses/" + course.id, { method: "DELETE" });
      setRevision((v) => v + 1);
    } catch (e) {
      setFailure((e as Error).message);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="YOUR CURRICULUM"
        title="我的课程"
        description="把每一门课的资料、思考与进展放在一起。"
        action={
          <button
            className="primary"
            onClick={() => {
              setEditing(null);
              setOpen(true);
            }}
          >
            <Plus size={17} />
            新建课程
          </button>
        }
      />
      <div className="filters" style={{ marginBottom: 25 }}>
        <select
          aria-label="筛选学期"
          value={semester}
          onChange={(e) => setSemester(e.target.value)}
        >
          <option value="">全部学期</option>
          {Array.from(new Set(courses.map((c) => c.semester))).map((s) => (
            <option key={s} value={s}>
              {s || "未设学期"}
            </option>
          ))}
        </select>
      </div>
      <ErrorMessage error={error || failure} />
      {loading ? (
        <Loading />
      ) : courses.length ? (
        <div className="course-grid">
          {courses
            .filter((c) => !semester || c.semester === semester)
            .map((course) => (
              <article
                className="course-card"
                key={course.id}
                style={
                  { "--course-color": course.color } as React.CSSProperties
                }
              >
                <div className="course-card-top">
                  <span className="course-symbol">
                    <BookOpen size={23} />
                  </span>
                  <span className="pill">{course.semester || "未设学期"}</span>
                </div>
                <span className="eyebrow">
                  {course.code || "PERSONAL COURSE"}
                </span>
                <h2>{course.name}</h2>
                <p>
                  {course.document_count || 0} 份资料 · {course.note_count || 0}{" "}
                  篇笔记 · {course.due_count || 0} 张待复习卡片
                </p>
                <div className="course-progress">
                  <span>已作答 {course.answered_count || 0} 题</span>
                  <span>
                    {course.answered_count
                      ? Math.round(
                          (100 * (course.correct_count || 0)) /
                            course.answered_count,
                        ) + "% 正确（含自评）"
                      : "尚无答题记录"}
                  </span>
                  <progress
                    aria-label={course.name + " 答题正确率"}
                    max={Math.max(1, course.answered_count || 0)}
                    value={course.correct_count || 0}
                  />
                </div>
                <div className="course-card-footer">
                  <Link to={"/library?course=" + course.id}>
                    进入课程 <ArrowUpRight size={15} />
                  </Link>
                  <div>
                    <button
                      className="icon-button"
                      aria-label={"编辑 " + course.name}
                      onClick={() => {
                        setEditing(course);
                        setOpen(true);
                      }}
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      className="icon-button"
                      aria-label={"删除 " + course.name}
                      onClick={() => remove(course)}
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
          title="从第一门课程开始"
          description="例如 COMP3340 · Machine Learning。课程名称和学期随时可以调整。"
        />
      )}
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? "编辑课程" : "新建课程"}
      >
        <form onSubmit={save} className="form-stack">
          <label>
            课程名称
            <input
              name="name"
              required
              maxLength={200}
              defaultValue={editing?.name}
              placeholder="Machine Learning"
            />
          </label>
          <div className="form-row">
            <label>
              课程代码
              <input
                name="code"
                defaultValue={editing?.code}
                placeholder="COMP3340"
              />
            </label>
            <label>
              学期
              <input
                name="semester"
                defaultValue={editing?.semester || "2026 Fall"}
                placeholder="2026 Fall"
              />
            </label>
          </div>
          <label>
            课程颜色
            <input
              type="color"
              name="color"
              defaultValue={editing?.color || "#3e6656"}
            />
          </label>
          <ErrorMessage error={failure} />
          <button className="primary" disabled={busy}>
            {busy ? "保存中…" : "保存课程"}
          </button>
        </form>
      </Modal>
    </>
  );
}

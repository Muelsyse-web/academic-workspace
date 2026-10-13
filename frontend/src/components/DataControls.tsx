import { useRef, useState } from "react";
import { Download, Database, Upload, ArchiveRestore } from "lucide-react";
import { api } from "../api";
import { ErrorMessage } from "./Shared";
type Preview = {
  status: string;
  counts: Record<string, number>;
  conflicts: Record<string, unknown>;
};
export function DataControls({ onChange }: { onChange: () => void }) {
  const [restoreFile, setRestoreFile] = useState<File | null>(null),
    [confirm, setConfirm] = useState(""),
    [portableFile, setPortableFile] = useState<File | null>(null),
    [preview, setPreview] = useState<Preview | null>(null),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [message, setMessage] = useState("");
  const restoreInput = useRef<HTMLInputElement>(null),
    portableInput = useRef<HTMLInputElement>(null);
  async function restore() {
    if (!restoreFile || confirm !== "RESTORE") return;
    setBusy("restore");
    setError("");
    setMessage("");
    const data = new FormData();
    data.append("archive", restoreFile);
    data.append("confirm", confirm);
    try {
      const result = await api<{
        recovery_path: string;
        interrupted_jobs: number;
      }>("/restore", { method: "POST", body: data });
      await api("/dashboard");
      setRestoreFile(null);
      setConfirm("");
      if (restoreInput.current) restoreInput.current.value = "";
      setMessage(
        `恢复完成。原库恢复点：${result.recovery_path}。本地模型密钥和 Agent 令牌需要重新配置。${result.interrupted_jobs ? ` ${result.interrupted_jobs} 项中断任务可手动重新索引。` : ""}`,
      );
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function importPortable(confirmed = false) {
    if (!portableFile) return;
    setBusy("import");
    setError("");
    setMessage("");
    const data = new FormData();
    data.append("archive", portableFile);
    if (confirmed) data.append("confirm", "IMPORT");
    try {
      const result = await api<Preview>("/portable/import", {
        method: "POST",
        body: data,
      });
      if (confirmed) {
        setPreview(null);
        setPortableFile(null);
        if (portableInput.current) portableInput.current.value = "";
        setMessage(
          "合并导入完成。现有课程和笔记保持不变，重复原件按内容去重。",
        );
        onChange();
      } else setPreview(result);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  return (
    <section className="settings-panel data-controls">
      <h2>
        <Database size={19} />
        备份与数据迁移
      </h2>
      <p>
        完整备份用于恢复整个知识库；便携数据包用于向现有知识库合并资料与学习记录。两种导入均会先校验内容。
      </p>
      <ErrorMessage error={error} />
      {message && (
        <div className="notice" role="status">
          {message}
        </div>
      )}
      <div className="data-grid">
        <section>
          <h3>完整备份</h3>
          <p>
            包含数据库、全部原件和校验清单。不包含模型密钥、Agent
            令牌或日志。最大 4 GiB。
          </p>
          <a className="button" href="/api/v1/backup">
            <Download size={16} />
            下载完整备份
          </a>
          <label>
            选择恢复备份
            <input
              ref={restoreInput}
              type="file"
              accept=".zip"
              disabled={Boolean(busy)}
              onChange={(e) => setRestoreFile(e.target.files?.[0] || null)}
            />
          </label>
          {restoreFile && (
            <div className="restore-confirm">
              <p>
                恢复将替换当前知识库，并保留原库恢复点。正在索引或生成回答时无法恢复。
              </p>
              <label>
                输入 RESTORE 确认替换
                <input
                  value={confirm}
                  disabled={Boolean(busy)}
                  onChange={(e) => setConfirm(e.target.value)}
                />
              </label>
              <button
                className="primary"
                disabled={confirm !== "RESTORE" || Boolean(busy)}
                onClick={restore}
              >
                <ArchiveRestore size={16} />
                {busy === "restore" ? "校验并恢复中…" : "恢复知识库"}
              </button>
            </div>
          )}
        </section>
        <section>
          <h3>便携数据包</h3>
          <p>
            包含可移植 JSON
            数据与原件。导入会重新映射关系，保留来源定位、笔记、对话及复习历史。
          </p>
          <a className="button" href="/api/v1/portable/export">
            <Download size={16} />
            导出便携数据
          </a>
          <label>
            选择便携数据包
            <input
              ref={portableInput}
              type="file"
              accept=".zip"
              disabled={Boolean(busy)}
              onChange={(e) => {
                setPortableFile(e.target.files?.[0] || null);
                setPreview(null);
              }}
            />
          </label>
          {portableFile && !preview && (
            <button
              disabled={Boolean(busy)}
              onClick={() => importPortable(false)}
            >
              <Upload size={16} />
              {busy === "import" ? "校验中…" : "预览导入内容"}
            </button>
          )}
          {preview && (
            <div className="import-preview">
              <h3>导入预览</h3>
              <dl>
                {Object.entries(preview.counts)
                  .filter(([, n]) => n > 0)
                  .map(([key, value]) => (
                    <div key={key}>
                      <dt>{key}</dt>
                      <dd>{value}</dd>
                    </div>
                  ))}
              </dl>
              <details>
                <summary>重复与冲突信息</summary>
                <pre>{JSON.stringify(preview.conflicts, null, 2)}</pre>
              </details>
              <button
                className="primary"
                disabled={Boolean(busy)}
                onClick={() => importPortable(true)}
              >
                {busy === "import" ? "合并中…" : "确认合并导入"}
              </button>
            </div>
          )}
        </section>
      </div>
    </section>
  );
}

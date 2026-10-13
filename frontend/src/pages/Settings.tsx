import { useEffect, useState, type FormEvent } from "react";
import {
  PlugZap,
  Save,
  Database,
  KeyRound,
  Download,
  Trash2,
  RefreshCw,
} from "lucide-react";
import { api, type Course } from "../api";
import { useData, PageHeading, ErrorMessage } from "../components/Shared";
type Config = {
  base_url: string;
  model: string;
  embedding_model: string;
  timeout: number;
  has_api_key: boolean;
};
type Token = { id: string; name: string; scope: string; created_at: string };
export function Settings() {
  const [revision, setRevision] = useState(0),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [models, setModels] = useState<string[]>([]),
    [issued, setIssued] = useState(""),
    [busy, setBusy] = useState(false);
  const { data: config, error: loadError } = useData<Config | null>(
      "/settings/provider",
      null,
      revision,
    ),
    { data: tokens } = useData<Token[]>("/agent-tokens", [], revision),
    { data: index } = useData<{
      status: string;
      progress: number;
      error?: string;
    }>("/embeddings/status", { status: "idle", progress: 0 }, revision);
  useEffect(() => {
    if (!["queued", "processing"].includes(index.status)) return;
    const timer = setInterval(() => setRevision((v) => v + 1), 1500);
    return () => clearInterval(timer);
  }, [index.status]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("");
    const f = new FormData(event.currentTarget);
    const payload = {
      base_url: f.get("base_url"),
      model: f.get("model"),
      embedding_model: f.get("embedding_model"),
      timeout: Number(f.get("timeout")),
      ...(f.get("api_key") ? { api_key: f.get("api_key") } : {}),
    };
    try {
      await api("/settings/provider", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      const result = await api<{
        available: boolean;
        models: string[];
        error?: string;
      }>("/settings/provider/test", { method: "POST" });
      setModels(result.models);
      setMessage(
        result.available
          ? "配置已保存，本地服务连接成功。"
          : "配置已保存。" + result.error,
      );
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function createToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    const f = new FormData(event.currentTarget);
    try {
      const result = await api<{ token: string }>("/agent-tokens", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(f)),
      });
      setIssued(result.token);
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function rebuild() {
    try {
      await api("/embeddings/reindex", { method: "POST" });
      setRevision((v) => v + 1);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <PageHeading
        eyebrow="YOUR WORKSPACE, YOUR RULES"
        title="设置"
        description="本地模型、Agent 访问与数据管理，保持清楚可控。"
      />
      <ErrorMessage error={error || loadError} />
      {message && (
        <div className="notice" role="status">
          {message}
        </div>
      )}
      <div className="settings-grid">
        <section className="settings-panel">
          <h2>
            <PlugZap size={19} />
            本地 AI 服务
          </h2>
          <p>
            支持 LM Studio、Ollama 和其他本地 OpenAI-compatible 服务。聊天与
            Embedding 模型分别选择。
          </p>
          {config && (
            <form className="form-stack" onSubmit={save}>
              <label>
                服务地址
                <input
                  name="base_url"
                  defaultValue={config.base_url}
                  required
                />
              </label>
              <div className="form-row">
                <label>
                  聊天模型
                  <input
                    name="model"
                    defaultValue={config.model}
                    list="local-models"
                    placeholder="模型 ID"
                  />
                </label>
                <label>
                  Embedding 模型
                  <input
                    name="embedding_model"
                    defaultValue={config.embedding_model}
                    list="local-models"
                    placeholder="多语言 embedding 模型 ID"
                  />
                </label>
              </div>
              <datalist id="local-models">
                {models.map((model) => (
                  <option value={model} key={model} />
                ))}
              </datalist>
              <div className="form-row">
                <label>
                  超时（秒）
                  <input
                    type="number"
                    name="timeout"
                    defaultValue={config.timeout}
                    min={3}
                    max={180}
                  />
                </label>
                <label>
                  本地服务密钥（可选）
                  <input
                    type="password"
                    name="api_key"
                    autoComplete="off"
                    placeholder={
                      config.has_api_key
                        ? "已保存；留空保持原值"
                        : "无密钥服务可留空"
                    }
                  />
                </label>
              </div>
              <div className="button-group">
                <button className="primary" disabled={busy}>
                  <Save size={16} />
                  {busy ? "检测中…" : "保存并检测连接"}
                </button>
                {config.has_api_key && (
                  <button
                    type="button"
                    onClick={async () => {
                      try {
                        await api("/settings/provider", {
                          method: "PUT",
                          body: JSON.stringify({ api_key: "" }),
                        });
                        setRevision((v) => v + 1);
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    清除密钥
                  </button>
                )}
              </div>
            </form>
          )}
          <div className="embedding-status">
            <h3>语义索引</h3>
            <p>
              {index.status} · {index.progress}% {index.error}
            </p>
            <button
              onClick={rebuild}
              disabled={["queued", "processing"].includes(index.status)}
            >
              <RefreshCw size={15} />
              构建 / 重建 Embedding 索引
            </button>
            <small>
              服务不可用时自动回退到关键词搜索。切换模型后需要重建。
            </small>
          </div>
        </section>
        <section className="settings-panel">
          <h2>
            <KeyRound size={19} />
            外部本地 Agent
          </h2>
          <p>
            让本机 Codex、OpenClaw 等通过 HTTP API
            读取知识库。令牌默认只读，撤销后立即失效。
          </p>
          <form className="form-stack" onSubmit={createToken}>
            <label>
              令牌名称
              <input
                name="name"
                required
                maxLength={100}
                placeholder="例如 Codex"
              />
            </label>
            <label>
              访问范围
              <select name="scope">
                <option value="read">只读：搜索与读取资料</option>
                <option value="write">读写：允许创建和修改学习内容</option>
              </select>
            </label>
            <button>创建访问令牌</button>
          </form>
          {issued && (
            <div className="issued-token">
              <strong>请复制保存，此值仅显示一次。</strong>
              <textarea aria-label="新建 Agent 令牌" readOnly value={issued} />
              <button onClick={() => setIssued("")}>已保存，隐藏令牌</button>
            </div>
          )}
          <div className="token-list">
            {tokens.map((token) => (
              <div key={token.id}>
                <span>
                  {token.name}
                  <small>{token.scope === "read" ? "只读" : "读写"}</small>
                </span>
                <button
                  className="icon-button"
                  aria-label={"撤销 " + token.name}
                  onClick={async () => {
                    try {
                      await api("/agent-tokens/" + token.id, {
                        method: "DELETE",
                      });
                      setRevision((v) => v + 1);
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
          <p className="subtle">
            API：/api/v1 · OpenAPI：/api/v1/openapi.json
            <br />
            Authorization: Bearer &lt;token&gt;
          </p>
        </section>
      </div>
    </>
  );
}

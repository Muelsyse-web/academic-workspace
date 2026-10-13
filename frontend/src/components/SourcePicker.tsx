import { useState } from "react";
import { locationLabel, type Document, type SourceUnit } from "../api";
import { ErrorMessage, Loading, Modal, useData } from "./Shared";

export type SourceRef = {
  document_id: string;
  version_id: string;
  locator_type: string;
  locator: number;
  quote: string;
};

export function SourcePicker({
  onAdd,
  onClose,
}: {
  onAdd: (source: SourceRef & { document_title: string }) => void;
  onClose: () => void;
}) {
  const [documentId, setDocumentId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [quote, setQuote] = useState("");
  const documents = useData<Document[]>("/documents", []);
  const units = useData<SourceUnit[]>(
    documentId ? `/documents/${encodeURIComponent(documentId)}/units` : null,
    [],
  );
  const document = documents.data.find((entry) => entry.id === documentId);
  const unit = units.data.find((entry) => entry.id === unitId);
  const valid = Boolean(
    document &&
    unit &&
    quote.trim() &&
    unit.text.includes(quote) &&
    !units.loading &&
    !units.error,
  );

  function add() {
    if (!valid || !document || !unit) return;
    onAdd({
      document_id: document.id,
      version_id: unit.version_id,
      locator_type: unit.locator_type,
      locator: unit.locator,
      quote,
      document_title: document.title,
    });
    onClose();
  }

  return (
    <Modal open onClose={onClose} title="添加资料引用">
      <div className="form-stack">
        <ErrorMessage error={documents.error || units.error} />
        {documents.loading ? (
          <Loading />
        ) : (
          <>
            <label>
              选择资料
              <select
                aria-label="选择资料"
                value={documentId}
                onChange={(event) => {
                  setDocumentId(event.target.value);
                  setUnitId("");
                  setQuote("");
                }}
              >
                <option value="">请选择资料</option>
                {documents.data.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    [{entry.kind?.toUpperCase() || "资料"}] {entry.title} ·{" "}
                    {entry.filename}
                  </option>
                ))}
              </select>
            </label>
            {!documents.error && !documents.data.length && (
              <p className="subtle">暂无资料，请先导入并完成索引。</p>
            )}
          </>
        )}
        {units.loading && <Loading />}
        {documentId && !units.loading && !units.error && (
          <>
            <label>
              选择原文位置
              <select
                aria-label="选择原文位置"
                value={unitId}
                onChange={(event) => {
                  setUnitId(event.target.value);
                  setQuote(
                    units.data.find((entry) => entry.id === event.target.value)
                      ?.text || "",
                  );
                }}
              >
                <option value="">请选择原文片段</option>
                {units.data.map((entry, index) => (
                  <option
                    key={entry.id}
                    value={entry.id}
                    disabled={!entry.text.trim()}
                  >
                    {locationLabel(entry.locator_type, entry.locator)} · 片段{" "}
                    {index + 1} · {entry.text.slice(0, 70) || "无文本"}
                  </option>
                ))}
              </select>
            </label>
            {!units.data.some((entry) => entry.text.trim()) && (
              <p className="subtle">
                此资料没有可引用的文本，请先完成索引或检查扫描件。
              </p>
            )}
          </>
        )}
        {unit && (
          <>
            <h3>原文 · {locationLabel(unit.locator_type, unit.locator)}</h3>
            <blockquote
              style={{
                whiteSpace: "pre-wrap",
                maxHeight: "35vh",
                overflow: "auto",
              }}
            >
              {unit.text}
            </blockquote>
            <label>
              引用摘录
              <textarea
                aria-label="引用摘录"
                value={quote}
                onChange={(event) => setQuote(event.target.value)}
              />
            </label>
            {!valid && (
              <p className="subtle">摘录必须是所选原文中的连续非空片段。</p>
            )}
          </>
        )}
        <div className="button-group">
          <button type="button" onClick={onClose}>
            取消
          </button>
          <button
            type="button"
            className="primary"
            disabled={!valid}
            onClick={add}
          >
            添加此引用
          </button>
        </div>
      </div>
    </Modal>
  );
}

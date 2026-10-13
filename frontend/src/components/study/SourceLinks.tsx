import { Link } from "react-router-dom";
import { locationLabel } from "../../api";
import type { SourceRef } from "./types";
export function SourceLinks({ sources }: { sources: SourceRef[] }) {
  return (
    <>
      {sources.map((s, index) => (
        <details className="citation-card" key={index}>
          <summary>
            来源 {index + 1} · {locationLabel(s.locator_type, s.locator)}
          </summary>
          <blockquote>{s.quote}</blockquote>
          <Link
            to={`/documents/${s.document_id}?version=${s.version_id}&locator=${s.locator}`}
          >
            查看原文 →
          </Link>
        </details>
      ))}
    </>
  );
}

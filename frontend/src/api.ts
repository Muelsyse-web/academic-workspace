let csrf = "";
let session: Promise<void> | null = null;
export async function connect() {
  if (!session)
    session = fetch("/api/v1/session", {
      method: "POST",
      credentials: "same-origin",
    })
      .then(async (response) => {
        if (!response.ok)
          throw new Error("无法建立本地会话，请检查服务和浏览器地址。");
        csrf = (await response.json()).csrf_token;
      })
      .catch((error) => {
        session = null;
        throw error;
      });
  return session;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
  retry = true,
): Promise<T> {
  await connect();
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  const requestCsrf = csrf;
  headers.set("X-CSRF-Token", requestCsrf);
  const response = await fetch("/api/v1" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = (await response.json()).detail;
    } catch {
      detail = response.statusText;
    }
    if (
      retry &&
      (response.status === 401 ||
        (response.status === 403 && detail === "CSRF token required"))
    ) {
      if (csrf === requestCsrf) {
        session = null;
        csrf = "";
      }
      return api<T>(path, options, false);
    }
    throw new Error(
      typeof detail === "string" ? detail : JSON.stringify(detail),
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}
export function post<T>(path: string, value: unknown) {
  return api<T>(path, { method: "POST", body: JSON.stringify(value) });
}
export type Course = {
  id: string;
  name: string;
  code: string;
  semester: string;
  color: string;
  document_count?: number;
  note_count?: number;
  card_count?: number;
  due_count?: number;
  answered_count?: number;
  correct_count?: number;
};
export type Document = {
  id: string;
  title: string;
  filename: string;
  relative_path?: string;
  kind: string;
  status: string;
  active_version: string | null;
  favorite: boolean;
  tags: string[];
  topic: string;
  course_ids: string[];
  related_ids: string[];
  error?: string;
};
export type SourceUnit = {
  id: string;
  version_id: string;
  locator_type: string;
  locator: number;
  heading: string;
  text: string;
};
export type SearchHit = {
  chunk_id: string;
  document_id: string;
  version_id: string;
  text: string;
  title: string;
  kind: string;
  locator_type: string;
  locator: number;
  heading: string;
};
export function locationLabel(type: string, position: number) {
  return `${({ page: "页", slide: "幻灯片", paragraph: "段落 / 表格", line: "起始行" } as Record<string, string>)[type] || type} ${position}`;
}

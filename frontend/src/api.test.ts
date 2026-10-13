import { it, expect, vi, afterEach } from "vitest";
afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});
it("reconnects and retries once when a restore invalidates the browser session", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: "old" })))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Local session required" }), {
        status: 401,
      }),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: "new" })))
    .mockResolvedValueOnce(new Response(JSON.stringify([{ id: "restored" }])));
  vi.stubGlobal("fetch", fetch);
  const { api } = await import("./api");
  expect(await api("/courses")).toEqual([{ id: "restored" }]);
  expect(fetch).toHaveBeenCalledTimes(4);
});

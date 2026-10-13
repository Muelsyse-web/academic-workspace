import { it, expect } from "vitest";
import { partitionUploads } from "./uploads";
it("keeps folder batches inside both count and byte budgets", () => {
  const files = Array.from({ length: 5 }, () => ({ size: 80 * 1024 * 1024 }));
  expect(partitionUploads(files).map((batch) => batch.length)).toEqual([
    2, 2, 1,
  ]);
  expect(
    partitionUploads(Array.from({ length: 101 }, () => ({ size: 1 }))).map(
      (b) => b.length,
    ),
  ).toEqual([100, 1]);
});
it("rejects an oversize file before any requests", () => {
  expect(() => partitionUploads([{ size: 101 * 1024 * 1024 }])).toThrow(
    /100 MiB/,
  );
});

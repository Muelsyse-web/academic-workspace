/** Bound folder batches before sending anything; backend enforces its own limits. */
export function partitionUploads<T extends { size: number }>(
  files: T[],
): T[][] {
  if (files.some((file) => file.size > 100 * 1024 * 1024))
    throw new Error("单文件不能超过 100 MiB。请分割较大的文档后导入。");
  const batches: T[][] = [];
  let current: T[] = [],
    bytes = 0;
  for (const file of files) {
    if (
      current.length &&
      (current.length >= 100 || bytes + file.size > 200 * 1024 * 1024)
    ) {
      batches.push(current);
      current = [];
      bytes = 0;
    }
    current.push(file);
    bytes += file.size;
  }
  if (current.length) batches.push(current);
  return batches;
}

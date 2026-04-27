/**
 * Convert an array of plain objects to a CSV string.
 * Header is the union of keys from the first row (or all rows if forceUnion).
 */
export function toCsv(
  rows: Record<string, unknown>[],
  options: { columns?: string[]; eol?: string } = {},
): string {
  const eol = options.eol ?? "\n";
  if (rows.length === 0 && !options.columns) return "";

  const columns =
    options.columns ??
    Array.from(
      rows.reduce<Set<string>>((set, r) => {
        Object.keys(r).forEach((k) => set.add(k));
        return set;
      }, new Set<string>()),
    );

  const escape = (v: unknown): string => {
    if (v === null || v === undefined) return "";
    let s: string;
    if (v instanceof Date) {
      s = v.toISOString();
    } else if (typeof v === "object") {
      s = JSON.stringify(v);
    } else {
      s = String(v);
    }
    if (s.includes(",") || s.includes('"') || s.includes("\n") || s.includes("\r")) {
      s = `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  };

  const lines = [columns.join(",")];
  for (const r of rows) {
    lines.push(columns.map((c) => escape(r[c])).join(","));
  }
  return lines.join(eol) + eol;
}

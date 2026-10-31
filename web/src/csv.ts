/** Tiny CSV reader for previewing a file in the browser before upload. The server
 * does the real parsing; this only lets you point at the right columns. */
export function sniffDelimiter(text: string): string {
  const sample = text.split(/\r?\n/).slice(0, 20).join("\n");
  const counts = [",", ";", "\t", "|"].map((d) => [d, sample.split(d).length] as const);
  return counts.sort((a, b) => b[1] - a[1])[0][0];
}

export function parseCsvRows(text: string, delimiter: string, maxRows = 30): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let i = 0; i < text.length && rows.length < maxRows; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === delimiter) { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); cell = "";
      if (row.some((c) => c.trim())) rows.push(row);
      row = [];
    } else cell += ch;
  }
  if ((cell || row.length) && rows.length < maxRows) { row.push(cell); if (row.some((c) => c.trim())) rows.push(row); }
  return rows;
}

export const DATE_FORMATS: [string, string][] = [
  ["%d/%m/%Y", "31/12/2026"],
  ["%d/%m/%y", "31/12/26"],
  ["%d-%m-%Y", "31-12-2026"],
  ["%d %b %Y", "31 Dec 2026"],
  ["%d-%b-%Y", "31-Dec-2026"],
  ["%d-%b-%y", "31-Dec-26"],
  ["%Y-%m-%d", "2026-12-31"],
  ["%m/%d/%Y", "12/31/2026"],
  ["%d.%m.%Y", "31.12.2026"],
];

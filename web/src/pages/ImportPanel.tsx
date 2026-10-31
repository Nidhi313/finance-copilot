import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, call, postForm, type Schemas } from "../api";
import { ErrorNote, Field } from "../components/ui";
import { DATE_FORMATS, parseCsvRows, sniffDelimiter } from "../csv";
import { money, shortDate } from "../format";
import { useAccounts, useCategories, useCountry } from "../hooks";

type Source = { kind: "preset"; id: string } | { kind: "saved"; id: string } | { kind: "mapping" };

export default function ImportPanel({ country, locale, onClose }: { country: string; locale: string; onClose: () => void }) {
  const qc = useQueryClient();
  const accounts = useAccounts(country);
  const ctx = useCountry(country);
  const categories = useCategories();
  const saved = useQuery({ queryKey: ["csv-mappings"], queryFn: () => call(api.GET("/v1/csv-mappings")) });
  const [accountId, setAccountId] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [source, setSource] = useState<Source | null>(null);
  const [headerRow, setHeaderRow] = useState<number | null>(0);
  const [m, setM] = useState({ date: "", desc: "", amount: "", debit: "", credit: "", split: false, invert: false, fmt: "%d/%m/%Y" });
  const [saveAs, setSaveAs] = useState("");

  const delimiter = useMemo(() => (text ? sniffDelimiter(text) : ","), [text]);
  const rows = useMemo(() => (text ? parseCsvRows(text, delimiter, 15) : []), [text, delimiter]);
  const hasHeader = headerRow !== null;
  const columns = hasHeader && rows[headerRow!]
    ? rows[headerRow!].map((h, i) => ({ value: h.trim() || String(i), label: h.trim() || `Column ${i + 1}` }))
    : (rows[0] ?? []).map((c, i) => ({ value: String(i), label: `Column ${i + 1} (e.g. ${c.slice(0, 18)})` }));

  const mapping = (): Schemas["CsvMapping"] => {
    const ref = (v: string) => (hasHeader ? v : Number(v));
    return {
      has_header: hasHeader,
      delimiter,
      date_column: ref(m.date),
      date_format: m.fmt,
      description_columns: [ref(m.desc)],
      amount_column: m.split ? null : ref(m.amount),
      debit_column: m.split && m.debit ? ref(m.debit) : null,
      credit_column: m.split && m.credit ? ref(m.credit) : null,
      invert_amounts: m.invert,
      decimal_separator: ".",
    };
  };

  const form = (): FormData => {
    const f = new FormData();
    f.append("file", file!);
    f.append("account_id", accountId);
    if (source?.kind === "preset") f.append("preset_id", source.id);
    if (source?.kind === "saved") f.append("saved_mapping_id", source.id);
    if (source?.kind === "mapping") {
      f.append("mapping", JSON.stringify(mapping()));
      if (saveAs.trim()) f.append("save_mapping_as", saveAs.trim());
    }
    return f;
  };

  const preview = useMutation({ mutationFn: () => postForm<Schemas["ImportPreviewOut"]>("/v1/imports/preview", form()) });
  const run = useMutation({
    mutationFn: () => postForm<{ import: Schemas["ImportOut"]; errors: { line: number; error: string }[] }>("/v1/imports", form()),
    onSuccess: () => qc.invalidateQueries(),
  });
  const account = accounts.data?.find((a) => a.id === accountId);
  const catName = new Map((categories.data ?? []).map((c) => [c.id, c.name]));
  const mappingReady = source?.kind !== "mapping" || (m.date && m.desc && (m.split ? m.debit || m.credit : m.amount));
  const ready = !!(file && accountId && source && mappingReady);

  if (run.data) {
    const r = run.data.import;
    return (
      <div className="stack">
        <div className="success">
          Imported {r.rows_imported} transaction{r.rows_imported === 1 ? "" : "s"} into {account?.name}.
          {r.rows_duplicate > 0 && ` ${r.rows_duplicate} were already there and were skipped.`}
          {r.rows_failed > 0 && ` ${r.rows_failed} line${r.rows_failed === 1 ? "" : "s"} could not be read.`}
        </div>
        <div className="row">
          <button className="btn" onClick={onClose}>Done</button>
        </div>
      </div>
    );
  }

  return (
    <div className="stack">
      <div className="form">
        <Field label="Into account">
          <select value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">Choose…</option>
            {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.currency})</option>)}
          </select>
        </Field>
        <Field label="Statement file (CSV)">
          <input type="file" accept=".csv,text/csv" onChange={async (e) => {
            const f = e.target.files?.[0] ?? null;
            setFile(f);
            setText(f ? await f.text() : "");
            preview.reset();
          }} />
        </Field>
        <Field label="Bank format">
          <select
            value={source ? `${source.kind}:${"id" in source ? source.id : ""}` : ""}
            onChange={(e) => {
              const [kind, id] = e.target.value.split(":");
              setSource(kind === "preset" ? { kind, id } : kind === "saved" ? { kind, id } : kind === "mapping" ? { kind } : null);
              preview.reset();
            }}
          >
            <option value="">Choose…</option>
            {ctx.data?.csv_presets.map((p) => (
              <option key={p.id} value={`preset:${p.id}`}>{p.bank_name}{p.verified ? "" : " (not yet verified)"}</option>
            ))}
            {saved.data?.map((s) => <option key={s.id} value={`saved:${s.id}`}>Saved: {s.name}</option>)}
            <option value="mapping:">My bank isn't listed: map the columns</option>
          </select>
        </Field>
      </div>

      {source?.kind === "mapping" && rows.length > 0 && (
        <div className="stack">
          <p className="small muted">
            Click the row that holds the column names, or choose "No header row". Then say which column is which.
          </p>
          <div className="table-wrap" style={{ maxHeight: 220, overflowY: "auto", border: "1px solid var(--line)", borderRadius: 6 }}>
            <table>
              <tbody>
                {rows.slice(0, 10).map((r, i) => (
                  <tr key={i} onClick={() => setHeaderRow(i)} style={{ cursor: "pointer", background: headerRow === i ? "var(--accent-soft)" : undefined }}>
                    {r.map((c, j) => <td key={j} className="small">{c}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="form">
            <Field label="Header row">
              <select value={headerRow === null ? "none" : String(headerRow)} onChange={(e) => setHeaderRow(e.target.value === "none" ? null : Number(e.target.value))}>
                <option value="none">No header row</option>
                {rows.slice(0, 10).map((_, i) => <option key={i} value={i}>Row {i + 1}</option>)}
              </select>
            </Field>
            {(["date", "desc"] as const).map((k) => (
              <Field key={k} label={k === "date" ? "Date column" : "Description column"}>
                <select value={m[k]} onChange={(e) => setM({ ...m, [k]: e.target.value })}>
                  <option value="">Choose…</option>
                  {columns.map((c) => <option key={c.value + c.label} value={c.value}>{c.label}</option>)}
                </select>
              </Field>
            ))}
            <Field label="Date looks like">
              <select value={m.fmt} onChange={(e) => setM({ ...m, fmt: e.target.value })}>
                {DATE_FORMATS.map(([f, ex]) => <option key={f} value={f}>{ex}</option>)}
              </select>
            </Field>
            <Field label="Amounts are">
              <select value={m.split ? "split" : "single"} onChange={(e) => setM({ ...m, split: e.target.value === "split" })}>
                <option value="single">One column, minus for money out</option>
                <option value="split">Separate money out and money in columns</option>
              </select>
            </Field>
            {!m.split ? (
              <Field label="Amount column">
                <select value={m.amount} onChange={(e) => setM({ ...m, amount: e.target.value })}>
                  <option value="">Choose…</option>
                  {columns.map((c) => <option key={c.value + c.label} value={c.value}>{c.label}</option>)}
                </select>
              </Field>
            ) : (
              (["debit", "credit"] as const).map((k) => (
                <Field key={k} label={k === "debit" ? "Money out column" : "Money in column"}>
                  <select value={m[k]} onChange={(e) => setM({ ...m, [k]: e.target.value })}>
                    <option value="">None</option>
                    {columns.map((c) => <option key={c.value + c.label} value={c.value}>{c.label}</option>)}
                  </select>
                </Field>
              ))
            )}
            <Field label="Save this format as" help="Optional, so next time it's one click">
              <input value={saveAs} onChange={(e) => setSaveAs(e.target.value)} placeholder="e.g. Kiwibank" />
            </Field>
          </div>
          <label className="checks"><span><input type="checkbox" checked={m.invert} onChange={(e) => setM({ ...m, invert: e.target.checked })} /> Purchases show as positive numbers (common for credit cards)</span></label>
        </div>
      )}

      <ErrorNote error={preview.error ?? run.error} />
      <div className="row">
        <button className="btn secondary" disabled={!ready || preview.isPending} onClick={() => preview.mutate()}>Preview</button>
        <button className="btn" disabled={!ready || !preview.data || run.isPending} onClick={() => run.mutate()}>
          {preview.data ? `Import ${preview.data.parsed} transactions` : "Import"}
        </button>
        <button className="btn link" onClick={onClose}>Cancel</button>
      </div>

      {preview.data && (
        <div className="stack">
          <p className="small muted">
            Read {preview.data.parsed} of {preview.data.total_lines} lines. Showing the first {preview.data.rows.length}. Nothing is saved until you import.
          </p>
          {preview.data.errors.length > 0 && (
            <div className="error">
              {preview.data.errors.length} line{preview.data.errors.length === 1 ? "" : "s"} could not be read and will be skipped. First:{" "}
              line {String(preview.data.errors[0].line)}: {String(preview.data.errors[0].error)}
            </div>
          )}
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Description</th><th>Category</th><th className="num">Amount</th></tr></thead>
              <tbody>
                {preview.data.rows.map((r) => (
                  <tr key={r.line}>
                    <td>{shortDate(r.date, locale)}</td>
                    <td>{r.description}</td>
                    <td className="muted">{r.category_id ? catName.get(r.category_id) : "Uncategorised"}</td>
                    <td className={`num ${Number(r.amount) < 0 ? "" : "pos"}`}>{money(r.amount, account?.currency ?? "AUD", locale)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api";
import { Card, Empty, ErrorNote, Field, PageHead } from "../components/ui";
import { money, shortDate, today } from "../format";
import { useAccounts, useActiveCountry, useCategories } from "../hooks";
import ImportPanel from "./ImportPanel";

const PAGE = 50;

function AddTransaction({ country }: { country: string }) {
  const qc = useQueryClient();
  const accounts = useAccounts(country);
  const categories = useCategories();
  const [f, setF] = useState({ account_id: "", date: today(), description: "", amount: "", direction: "out", category_id: "" });
  const add = useMutation({
    mutationFn: () => {
      const amt = Math.abs(Number(f.amount));
      return call(api.POST("/v1/transactions", { body: {
        account_id: f.account_id || accounts.data![0].id, date: f.date, description: f.description,
        amount: String(f.direction === "out" ? -amt : amt), category_id: f.category_id || null,
      } }));
    },
    onSuccess: () => { qc.invalidateQueries(); setF({ ...f, description: "", amount: "", category_id: "" }); },
  });
  if (!accounts.data?.length) return <Empty>Add an account in this country first.</Empty>;
  return (
    <form className="stack" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
      <div className="form">
        <Field label="Account">
          <select value={f.account_id} onChange={(e) => setF({ ...f, account_id: e.target.value })}>
            {accounts.data.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </Field>
        <Field label="Date"><input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} required /></Field>
        <Field label="Description"><input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} required /></Field>
        <Field label="Money">
          <select value={f.direction} onChange={(e) => setF({ ...f, direction: e.target.value })}>
            <option value="out">Out</option>
            <option value="in">In</option>
          </select>
        </Field>
        <Field label="Amount"><input type="number" min="0" step="0.01" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} required /></Field>
        <Field label="Category" help="Leave empty to use your rules">
          <select value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })}>
            <option value="">Automatic</option>
            {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <button className="btn" disabled={add.isPending}>Add</button>
      </div>
      <ErrorNote error={add.error} />
    </form>
  );
}

export default function Transactions() {
  const { code, ctx, locale } = useActiveCountry();
  const qc = useQueryClient();
  const accounts = useAccounts(code ?? undefined);
  const categories = useCategories();
  const [filters, setFilters] = useState({ account_id: "", search: "", uncategorised: false });
  const [offset, setOffset] = useState(0);
  const [mode, setMode] = useState<"none" | "add" | "import">("none");

  const txns = useQuery({
    queryKey: ["transactions", code, filters, offset],
    queryFn: () => call(api.GET("/v1/transactions", { params: { query: {
      country: code!, account_id: filters.account_id || undefined, search: filters.search || undefined,
      uncategorised: filters.uncategorised, limit: PAGE, offset,
    } } })),
    enabled: !!code,
    placeholderData: keepPreviousData,
  });
  const setCategory = useMutation({
    mutationFn: ({ id, category_id }: { id: string; category_id: string }) =>
      call(api.PATCH("/v1/transactions/{txn_id}", { params: { path: { txn_id: id } },
        body: category_id ? { category_id } : { clear_category: true } })),
    onSuccess: () => qc.invalidateQueries(),
  });
  const applyRules = useMutation({
    mutationFn: () => call(api.POST("/v1/category-rules/apply")),
    onSuccess: () => qc.invalidateQueries(),
  });
  const remove = useMutation({
    mutationFn: (id: string) => call(api.DELETE("/v1/transactions/{txn_id}", { params: { path: { txn_id: id } } })),
    onSuccess: () => qc.invalidateQueries(),
  });
  const accName = new Map((accounts.data ?? []).map((a) => [a.id, a.name]));
  const total = txns.data?.total ?? 0;

  return (
    <>
      <PageHead
        title="Transactions"
        sub={ctx ? `In ${ctx.name}` : undefined}
        action={
          <div className="row">
            <button className="btn secondary" onClick={() => setMode(mode === "add" ? "none" : "add")}>Add one</button>
            <button className="btn" onClick={() => setMode(mode === "import" ? "none" : "import")}>Import a statement</button>
          </div>
        }
      />
      {mode === "add" && code && <Card title="Add a transaction"><AddTransaction country={code} /></Card>}
      {mode === "import" && code && (
        <Card title="Import a bank statement" sub="Re-importing the same file is safe: rows already imported are skipped.">
          <ImportPanel country={code} locale={locale} onClose={() => setMode("none")} />
        </Card>
      )}
      <Card>
        <div className="row" style={{ marginBottom: 12 }}>
          <select className="input" value={filters.account_id} onChange={(e) => { setOffset(0); setFilters({ ...filters, account_id: e.target.value }); }}>
            <option value="">All accounts</option>
            {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
          <input className="input" placeholder="Search descriptions" value={filters.search}
            onChange={(e) => { setOffset(0); setFilters({ ...filters, search: e.target.value }); }} />
          <label className="checks"><span>
            <input type="checkbox" checked={filters.uncategorised} onChange={(e) => { setOffset(0); setFilters({ ...filters, uncategorised: e.target.checked }); }} /> Uncategorised only
          </span></label>
          <span style={{ flex: 1 }} />
          <button className="btn secondary" onClick={() => applyRules.mutate()} disabled={applyRules.isPending}>Apply category rules</button>
        </div>
        {applyRules.data && <p className="small muted">Categorised {applyRules.data.categorised} transactions.</p>}
        <ErrorNote error={txns.error ?? setCategory.error} />
        {txns.data?.items.length === 0 ? (
          <Empty>No transactions match. Add one or import a statement.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Description</th><th>Account</th><th>Category</th><th className="num">Amount</th><th /></tr></thead>
              <tbody>
                {txns.data?.items.map((t) => (
                  <tr key={t.id}>
                    <td style={{ whiteSpace: "nowrap" }}>{shortDate(t.date, locale)}</td>
                    <td>{t.description}</td>
                    <td className="small muted">{accName.get(t.account_id)}</td>
                    <td>
                      <select aria-label="Category" value={t.category_id ?? ""} onChange={(e) => setCategory.mutate({ id: t.id, category_id: e.target.value })}>
                        <option value="">Uncategorised</option>
                        {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    </td>
                    <td className={`num ${Number(t.amount) > 0 ? "pos" : ""}`}>{money(t.amount, t.currency || "AUD", locale, { sign: Number(t.amount) > 0 })}</td>
                    <td className="num"><button className="btn link" onClick={() => remove.mutate(t.id)} aria-label={`Delete ${t.description}`}>Delete</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {total > PAGE && (
          <div className="row" style={{ marginTop: 12 }}>
            <button className="btn secondary" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Newer</button>
            <span className="small muted">{offset + 1} to {Math.min(offset + PAGE, total)} of {total}</span>
            <button className="btn secondary" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>Older</button>
          </div>
        )}
      </Card>
    </>
  );
}

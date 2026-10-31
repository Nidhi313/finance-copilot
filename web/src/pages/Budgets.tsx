import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api";
import { Card, Empty, ErrorNote, Field, PageHead, Progress } from "../components/ui";
import { money, num, thisMonth } from "../format";
import { useActiveCountry, useCategories } from "../hooks";

export default function Budgets() {
  const { code, ctx, locale } = useActiveCountry();
  const qc = useQueryClient();
  const categories = useCategories();
  const [month, setMonth] = useState(thisMonth());
  const [f, setF] = useState({ category_id: "", amount: "" });
  const status = useQuery({
    queryKey: ["budget-status", code, month],
    queryFn: () => call(api.GET("/v1/budgets/status", { params: { query: { country: code!, month } } })),
    enabled: !!code,
  });
  const save = useMutation({
    mutationFn: () => call(api.PUT("/v1/budgets", { body: { country_code: code!, category_id: f.category_id, amount: f.amount } })),
    onSuccess: () => { qc.invalidateQueries(); setF({ category_id: "", amount: "" }); },
  });
  const remove = useMutation({
    mutationFn: (id: string) => call(api.DELETE("/v1/budgets/{budget_id}", { params: { path: { budget_id: id } } })),
    onSuccess: () => qc.invalidateQueries(),
  });
  const expenseCats = categories.data?.filter((c) => c.kind === "expense") ?? [];
  const totalBudget = (status.data ?? []).reduce((s, b) => s + num(b.budget), 0);
  const totalSpent = (status.data ?? []).reduce((s, b) => s + num(b.spent), 0);
  const cur = ctx?.currency ?? "AUD";

  return (
    <>
      <PageHead
        title="Budgets"
        sub={`Monthly budgets for ${ctx?.name ?? ""}, in ${cur}`}
        action={<input className="input" type="month" value={month} onChange={(e) => setMonth(e.target.value)} aria-label="Month" />}
      />
      <Card
        title={status.data?.length ? `${money(totalSpent, cur, locale, { decimals: 0 })} spent of ${money(totalBudget, cur, locale, { decimals: 0 })}` : "This month"}
      >
        <ErrorNote error={status.error} />
        {status.data?.length === 0 && <Empty>No budgets yet. Set one below. Each budget repeats every month.</Empty>}
        <div className="stack">
          {status.data?.map((b) => (
            <div key={b.budget_id} className="stack" style={{ gap: 6 }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong>{b.category}</strong>
                <span className="row small">
                  <span className={num(b.remaining) < 0 ? "neg" : "muted"}>
                    {num(b.remaining) < 0
                      ? `${money(-num(b.remaining), b.currency, locale)} over`
                      : `${money(b.remaining, b.currency, locale)} left`}
                  </span>
                  <span>{money(b.spent, b.currency, locale)} / {money(b.budget, b.currency, locale)}</span>
                  <button className="btn link" onClick={() => remove.mutate(b.budget_id)}>Remove</button>
                </span>
              </div>
              <Progress percent={num(b.percent_used)} />
            </div>
          ))}
        </div>
      </Card>
      <Card title="Set a budget" sub="Setting a budget for a category that already has one changes the amount.">
        <form className="form" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
          <Field label="Category">
            <select value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })} required>
              <option value="">Choose…</option>
              {expenseCats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label={`Per month (${cur})`}>
            <input type="number" min="0" step="1" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} required />
          </Field>
          <button className="btn" disabled={save.isPending}>Save budget</button>
        </form>
        <ErrorNote error={save.error} />
      </Card>
    </>
  );
}

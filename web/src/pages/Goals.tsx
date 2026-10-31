import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api";
import { Card, Empty, ErrorNote, Field, PageHead, Progress } from "../components/ui";
import { money, num, shortDate } from "../format";
import { useAccounts, useActiveCountry, useLocaleForCurrency, useMe } from "../hooks";

export default function Goals() {
  const me = useMe();
  const qc = useQueryClient();
  const { locale } = useActiveCountry();
  const localeFor = useLocaleForCurrency();
  const accounts = useAccounts();
  const goals = useQuery({ queryKey: ["goals"], queryFn: () => call(api.GET("/v1/goals")) });
  const [f, setF] = useState({ name: "", target_amount: "", currency: me.data?.home_currency ?? "AUD", target_date: "", account_id: "", saved_amount: "0" });
  const add = useMutation({
    mutationFn: () => call(api.POST("/v1/goals", { body: {
      ...f, target_date: f.target_date || null, account_id: f.account_id || null,
    } })),
    onSuccess: () => { qc.invalidateQueries(); setF({ ...f, name: "", target_amount: "", target_date: "" }); },
  });
  const remove = useMutation({
    mutationFn: (id: string) => call(api.DELETE("/v1/goals/{goal_id}", { params: { path: { goal_id: id } } })),
    onSuccess: () => qc.invalidateQueries(),
  });
  const currencies = [...new Set([me.data?.home_currency ?? "AUD", ...(accounts.data ?? []).map((a) => a.currency)])];

  return (
    <>
      <PageHead title="Goals" sub="Save towards something specific. Link an account and progress updates on its own." />
      {goals.data?.length === 0 && <Card><Empty>No goals yet. A trip home, a house deposit, a buffer for visa costs: add one below.</Empty></Card>}
      <div className="grid-2">
        {goals.data?.map((g) => (
          <Card key={g.id} title={g.name} sub={g.target_date ? `By ${shortDate(g.target_date, locale)}` : "No deadline"}
            action={<button className="btn link" onClick={() => remove.mutate(g.id)}>Remove</button>}>
            <div className="stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <span className="big-number" style={{ fontSize: 26 }}>{money(g.current, g.currency, localeFor(g.currency), { decimals: 0 })}</span>
                <span className="muted">of {money(g.target_amount, g.currency, localeFor(g.currency), { decimals: 0 })}</span>
              </div>
              <Progress percent={num(g.percent)} />
              {g.monthly_needed && num(g.monthly_needed) > 0 && (
                <p className="small muted">About {money(g.monthly_needed, g.currency, localeFor(g.currency), { decimals: 0 })} a month gets you there on time.</p>
              )}
              {g.current === null && <p className="small muted">The linked account's currency has no exchange rate yet.</p>}
            </div>
          </Card>
        ))}
      </div>
      <Card title="Add a goal">
        <form className="form" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Name"><input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required placeholder="Trip home" /></Field>
          <Field label="Target"><input type="number" min="0" step="1" value={f.target_amount} onChange={(e) => setF({ ...f, target_amount: e.target.value })} required /></Field>
          <Field label="Currency">
            <select value={f.currency} onChange={(e) => setF({ ...f, currency: e.target.value })}>
              {currencies.map((c) => <option key={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="By when"><input type="date" value={f.target_date} onChange={(e) => setF({ ...f, target_date: e.target.value })} /></Field>
          <Field label="Linked account" help="Its balance counts as progress">
            <select value={f.account_id} onChange={(e) => setF({ ...f, account_id: e.target.value })}>
              <option value="">None, I'll enter it</option>
              {accounts.data?.map((a) => <option key={a.id} value={a.id}>{a.name} ({a.currency})</option>)}
            </select>
          </Field>
          {!f.account_id && (
            <Field label="Saved so far"><input type="number" min="0" step="1" value={f.saved_amount} onChange={(e) => setF({ ...f, saved_amount: e.target.value })} /></Field>
          )}
          <button className="btn" disabled={add.isPending}>Add goal</button>
        </form>
        <ErrorNote error={add.error} />
      </Card>
    </>
  );
}

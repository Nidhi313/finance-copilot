import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api";
import { Card, Empty, ErrorNote, Field, PageHead } from "../components/ui";
import { money } from "../format";
import { useAccounts, useActiveCountry, useCountries, useCountry, useMe } from "../hooks";

function AddAccount({ defaultCountry }: { defaultCountry: string }) {
  const me = useMe();
  const qc = useQueryClient();
  const countries = useCountries();
  const [country, setCountry] = useState(defaultCountry);
  const ctx = useCountry(country);
  const [form, setForm] = useState({ name: "", type: "bank", institution: "", opening_balance: "0" });
  const add = useMutation({
    mutationFn: () => call(api.POST("/v1/accounts", { body: { country_code: country, ...form } })),
    onSuccess: () => {
      qc.invalidateQueries();
      setForm({ name: "", type: "bank", institution: "", opening_balance: "0" });
    },
  });
  const names = new Map((countries.data ?? []).map((c) => [c.code, c.name]));
  return (
    <form className="stack" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
      <div className="form">
        <Field label="Country">
          <select value={country} onChange={(e) => setCountry(e.target.value)}>
            {me.data?.countries.map((l) => <option key={l.country_code} value={l.country_code}>{names.get(l.country_code)}</option>)}
          </select>
        </Field>
        <Field label="Account name">
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required placeholder="Everyday account" />
        </Field>
        <Field label="Type">
          <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            {ctx.data?.account_types.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
        </Field>
        <Field label="Bank or provider">
          <input value={form.institution} onChange={(e) => setForm({ ...form, institution: e.target.value })} placeholder="Optional" />
        </Field>
        <Field label={`Balance today (${ctx.data?.currency ?? ""})`} help="Before any transactions you add or import">
          <input type="number" step="0.01" value={form.opening_balance} onChange={(e) => setForm({ ...form, opening_balance: e.target.value })} />
        </Field>
        <button className="btn" disabled={add.isPending}>Add account</button>
      </div>
      <ErrorNote error={add.error} />
    </form>
  );
}

export default function Accounts() {
  const { code, ctx, locale } = useActiveCountry();
  const [all, setAll] = useState(false);
  const accounts = useAccounts(all ? undefined : code ?? undefined);
  const countries = useCountries();
  const qc = useQueryClient();
  const names = new Map((countries.data ?? []).map((c) => [c.code, c]));
  const typeLabel = new Map((ctx?.account_types ?? []).map((t) => [t.key, t.label]));
  const archive = useMutation({
    mutationFn: (id: string) => call(api.PATCH("/v1/accounts/{account_id}", { params: { path: { account_id: id } }, body: { archived: true } })),
    onSuccess: () => qc.invalidateQueries(),
  });

  return (
    <>
      <PageHead
        title="Accounts"
        sub={all ? "All your countries" : `Accounts in ${ctx?.name ?? ""}`}
        action={<button className="btn secondary" onClick={() => setAll(!all)}>{all ? `Only ${ctx?.name ?? ""}` : "Show all countries"}</button>}
      />
      <Card>
        <ErrorNote error={accounts.error} />
        {accounts.data?.length === 0 ? (
          <Empty>No accounts here yet. Add one below.</Empty>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Account</th><th>Type</th>{all && <th>Country</th>}<th className="num">Balance</th><th /></tr>
              </thead>
              <tbody>
                {accounts.data?.map((a) => (
                  <tr key={a.id}>
                    <td>
                      {a.name}
                      {a.institution && <div className="small muted">{a.institution}</div>}
                    </td>
                    <td><span className="tag">{typeLabel.get(a.type) ?? a.type}</span></td>
                    {all && <td>{names.get(a.country_code)?.name}</td>}
                    <td className={`num ${Number(a.balance) < 0 ? "neg" : ""}`}>
                      {money(a.balance, a.currency, names.get(a.country_code)?.locale ?? locale)}
                    </td>
                    <td className="num">
                      <button className="btn link" onClick={() => archive.mutate(a.id)}>Archive</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      {code && (
        <Card title="Add an account" sub="Account types come from the country. Countries without local detail get the standard types.">
          <AddAccount key={code} defaultCountry={code} />
        </Card>
      )}
    </>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, API_URL, call } from "../api";
import { AddCountry } from "../components/CountryPicker";
import { Card, ErrorNote, Field, PageHead } from "../components/ui";
import { RELATIONSHIP_LABELS } from "../format";
import { keys, useCategories, useCountries, useMe } from "../hooks";

function Rules() {
  const qc = useQueryClient();
  const categories = useCategories();
  const rules = useQuery({ queryKey: ["rules"], queryFn: () => call(api.GET("/v1/category-rules")) });
  const [f, setF] = useState({ pattern: "", category_id: "" });
  const add = useMutation({
    mutationFn: () => call(api.POST("/v1/category-rules", { body: { ...f, priority: 100 } })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["rules"] }); setF({ pattern: "", category_id: "" }); },
  });
  const remove = useMutation({
    mutationFn: (id: string) => call(api.DELETE("/v1/category-rules/{rule_id}", { params: { path: { rule_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rules"] }),
  });
  const name = new Map((categories.data ?? []).map((c) => [c.id, c.name]));
  return (
    <Card title="Category rules" sub="Your rules run before each country's built-in ones. Matching is on part of the description, ignoring case.">
      <div className="stack">
        {rules.data?.map((r) => (
          <div key={r.id} className="row">
            <span>Descriptions containing <strong>"{r.pattern}"</strong> go to <strong>{name.get(r.category_id)}</strong></span>
            <button className="btn link" onClick={() => remove.mutate(r.id)}>Remove</button>
          </div>
        ))}
        <form className="form" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <Field label="Description contains"><input value={f.pattern} onChange={(e) => setF({ ...f, pattern: e.target.value })} required minLength={2} placeholder="e.g. landlord" /></Field>
          <Field label="Category">
            <select value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })} required>
              <option value="">Choose…</option>
              {categories.data?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <button className="btn" disabled={add.isPending}>Add rule</button>
        </form>
        <ErrorNote error={add.error} />
      </div>
    </Card>
  );
}

export default function Settings() {
  const me = useMe();
  const qc = useQueryClient();
  const countries = useCountries();
  const byCode = new Map((countries.data ?? []).map((c) => [c.code, c]));
  const currencies = [...new Set((countries.data ?? []).map((c) => c.currency))].sort();
  const update = useMutation({
    mutationFn: (home_currency: string) => call(api.PATCH("/v1/me", { body: { home_currency } })),
    onSuccess: (d) => { qc.setQueryData(keys.me, d); qc.invalidateQueries(); },
  });
  const unlink = useMutation({
    mutationFn: (code: string) => call(api.DELETE("/v1/me/countries/{code}", { params: { path: { code } } })),
    onSuccess: (d) => { qc.setQueryData(keys.me, d); qc.invalidateQueries(); },
  });
  const deleteMe = useMutation({
    mutationFn: () => call(api.DELETE("/v1/me")),
    onSuccess: () => qc.invalidateQueries(),
  });
  const [confirm, setConfirm] = useState("");

  return (
    <>
      <PageHead title="Countries and settings" />
      <Card title="Your countries" sub="Any country works. Ones marked 'basic support' have the standard features; local detail is added over time.">
        <div className="stack">
          {me.data?.countries.map((l) => {
            const c = byCode.get(l.country_code);
            return (
              <div key={l.country_code} className="row" style={{ justifyContent: "space-between", borderBottom: "1px solid var(--soft)", paddingBottom: 10 }}>
                <div>
                  <strong>{c?.name}</strong> <span className="muted">{c?.currency}</span>{" "}
                  {!c?.has_pack && <span className="tag">basic support</span>}
                  <div className="small muted">{l.relationships.map((r) => RELATIONSHIP_LABELS[r] ?? r).join(", ") || "No relationship set"}</div>
                </div>
                <button className="btn link" onClick={() => unlink.mutate(l.country_code)}>Remove</button>
              </div>
            );
          })}
          <ErrorNote error={unlink.error} />
          <h3>Add a country</h3>
          <AddCountry exclude={me.data?.countries.map((l) => l.country_code)} />
        </div>
      </Card>
      <Card title="Home currency" sub="Net worth, goals and transfer totals are shown in this currency.">
        <Field label="Currency">
          <select value={me.data?.home_currency} onChange={(e) => update.mutate(e.target.value)} style={{ maxWidth: 200 }}>
            {currencies.map((c) => <option key={c}>{c}</option>)}
          </select>
        </Field>
      </Card>
      <Rules />
      <Card title="Your data">
        <div className="stack">
          <p>Download everything stored about you as CSV files, or delete your account and all its data for good.</p>
          <div className="row">
            <a className="btn secondary" href={`${API_URL}/v1/me/export`}>Download my data</a>
          </div>
          <div className="row">
            <input className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder='Type "delete" to confirm' aria-label="Confirm delete" />
            <button className="btn danger" disabled={confirm !== "delete" || deleteMe.isPending} onClick={() => deleteMe.mutate()}>Delete my account</button>
          </div>
          <ErrorNote error={deleteMe.error} />
        </div>
      </Card>
    </>
  );
}

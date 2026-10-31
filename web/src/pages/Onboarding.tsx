import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api";
import { AddCountry } from "../components/CountryPicker";
import { Card, ErrorNote, Field } from "../components/ui";
import { keys, useCountries } from "../hooks";

export default function Onboarding() {
  const qc = useQueryClient();
  const countries = useCountries();
  const [currency, setCurrency] = useState("AUD");
  const currencies = [...new Set((countries.data ?? []).map((c) => c.currency))].sort();
  const save = useMutation({
    mutationFn: () => call(api.PATCH("/v1/me", { body: { home_currency: currency } })),
    onSuccess: (data) => qc.setQueryData(keys.me, data),
  });
  return (
    <main className="content" style={{ maxWidth: 720, margin: "0 auto", paddingTop: 48 }}>
      <div className="stack">
        <h1>Your money, across every country you live in</h1>
        <p className="muted">
          Start with the countries you live in, bank in or send money to. You can add more later, and any country works.
          Australia and India have extra local detail today.
        </p>
      </div>
      <Card title="Your home currency" sub="Net worth and totals are shown in this currency. You can change it any time.">
        <div className="row">
          <Field label="Currency">
            <select value={currency} onChange={(e) => setCurrency(e.target.value)}>
              {currencies.map((c) => <option key={c}>{c}</option>)}
            </select>
          </Field>
          <button className="btn secondary" onClick={() => save.mutate()} disabled={save.isPending}>
            {save.isSuccess ? "Saved" : "Save"}
          </button>
        </div>
        <ErrorNote error={save.error} />
      </Card>
      <Card title="Add your first country">
        <AddCountry />
      </Card>
    </main>
  );
}

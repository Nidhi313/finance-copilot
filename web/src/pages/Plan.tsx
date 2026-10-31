import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, call, type Schemas } from "../api";
import { Card, Disclaimer, ErrorNote, Field, PageHead } from "../components/ui";
import { money, num } from "../format";
import { useActiveCountry } from "../hooks";

type Calc = "compound_growth" | "regular_investing" | "emergency_fund" | "loan_repayment";
type Point = { year: number; contributed: string; value: string };
const ORDER: Calc[] = ["regular_investing", "compound_growth", "loan_repayment", "emergency_fund"];

function GrowthChart({ series, cur, locale, contributedLabel }: { series: Point[]; cur: string; locale: string; contributedLabel: string }) {
  return (
    <div style={{ width: "100%", height: 260 }}>
      <ResponsiveContainer>
        <LineChart data={series.map((p) => ({ year: `Year ${p.year}`, [contributedLabel]: num(p.contributed), Value: num(p.value) }))}>
          <CartesianGrid vertical={false} stroke="#eaefed" />
          <XAxis dataKey="year" fontSize={12} tickLine={false} axisLine={false} interval="preserveStartEnd" />
          <YAxis fontSize={12} tickLine={false} axisLine={false} width={70} tickFormatter={(v) => money(v, cur, locale, { decimals: 0 })} />
          <Tooltip formatter={(v: number) => money(v, cur, locale, { decimals: 0 })} />
          <Legend iconType="plainline" />
          <Line type="monotone" dataKey={contributedLabel} stroke="#8fa9a6" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="Value" stroke="#10282e" strokeWidth={2.5} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="small muted">{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700 }}>{value}</div>
    </div>
  );
}

export default function Plan() {
  const { code, ctx, locale } = useActiveCountry();
  const [tab, setTab] = useState<Calc>("regular_investing");
  const [inputs, setInputs] = useState<Record<string, string>>({
    monthly_amount: "500", annual_return_pct: "7", years: "10", annual_step_up_pct: "0",
    principal: "10000", monthly_contribution: "200", annual_rate_pct: "6",
    loan_principal: "50000", loan_rate: "9", loan_years: "5", extra_monthly: "0",
    months_target: "6", monthly_expenses: "", current_savings: "",
  });
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) => setInputs({ ...inputs, [k]: e.target.value });
  const cur = ctx?.currency ?? "AUD";

  const run = useMutation({
    mutationFn: (calc: Calc): Promise<Schemas["CalcOut"]> => {
      const c = code!;
      if (calc === "regular_investing")
        return call(api.POST("/v1/calculators/regular-investing", { body: { country_code: c, monthly_amount: inputs.monthly_amount,
          annual_return_pct: inputs.annual_return_pct, years: Number(inputs.years), annual_step_up_pct: inputs.annual_step_up_pct } }));
      if (calc === "compound_growth")
        return call(api.POST("/v1/calculators/compound-growth", { body: { country_code: c, principal: inputs.principal,
          monthly_contribution: inputs.monthly_contribution, annual_rate_pct: inputs.annual_rate_pct, years: Number(inputs.years) } }));
      if (calc === "loan_repayment")
        return call(api.POST("/v1/calculators/loan-repayment", { body: { country_code: c, principal: inputs.loan_principal,
          annual_rate_pct: inputs.loan_rate, years: Number(inputs.loan_years), extra_monthly: inputs.extra_monthly } }));
      return call(api.POST("/v1/calculators/emergency-fund", { body: { country_code: c, months_target: Number(inputs.months_target),
        monthly_expenses: inputs.monthly_expenses || null, current_savings: inputs.current_savings || null } }));
    },
  });
  const r = run.data?.calculator === tab ? (run.data.result as Record<string, unknown>) : null;
  const label = (k: Calc) => ctx?.calculator_labels[k] ?? k;

  return (
    <>
      <PageHead title="Plan" sub={`Calculators for ${ctx?.name ?? ""}. They simulate the numbers you enter; they don't tell you what to do.`} />
      <div className="tabs" role="tablist">
        {ORDER.map((k) => (
          <button key={k} role="tab" className="tab" aria-selected={tab === k} onClick={() => { setTab(k); run.reset(); }}>{label(k)}</button>
        ))}
      </div>
      <Card>
        <form className="stack" onSubmit={(e) => { e.preventDefault(); run.mutate(tab); }}>
          <div className="form">
            {tab === "regular_investing" && <>
              <Field label={`Each month (${cur})`}><input type="number" min="0" value={inputs.monthly_amount} onChange={set("monthly_amount")} /></Field>
              <Field label="Assumed yearly return (%)" help="Your assumption, not a forecast"><input type="number" min="0" max="100" step="0.1" value={inputs.annual_return_pct} onChange={set("annual_return_pct")} /></Field>
              <Field label="Years"><input type="number" min="1" max="60" value={inputs.years} onChange={set("years")} /></Field>
              <Field label="Raise the amount each year by (%)"><input type="number" min="0" max="100" step="1" value={inputs.annual_step_up_pct} onChange={set("annual_step_up_pct")} /></Field>
            </>}
            {tab === "compound_growth" && <>
              <Field label={`Starting amount (${cur})`}><input type="number" min="0" value={inputs.principal} onChange={set("principal")} /></Field>
              <Field label={`Added each month (${cur})`}><input type="number" min="0" value={inputs.monthly_contribution} onChange={set("monthly_contribution")} /></Field>
              <Field label="Yearly interest or return (%)"><input type="number" min="0" max="100" step="0.1" value={inputs.annual_rate_pct} onChange={set("annual_rate_pct")} /></Field>
              <Field label="Years"><input type="number" min="1" max="60" value={inputs.years} onChange={set("years")} /></Field>
            </>}
            {tab === "loan_repayment" && <>
              <Field label={`Loan amount (${cur})`}><input type="number" min="0" value={inputs.loan_principal} onChange={set("loan_principal")} /></Field>
              <Field label="Interest rate (% a year)"><input type="number" min="0" max="100" step="0.01" value={inputs.loan_rate} onChange={set("loan_rate")} /></Field>
              <Field label="Term (years)"><input type="number" min="1" max="60" value={inputs.loan_years} onChange={set("loan_years")} /></Field>
              <Field label={`Extra each month (${cur})`}><input type="number" min="0" value={inputs.extra_monthly} onChange={set("extra_monthly")} /></Field>
            </>}
            {tab === "emergency_fund" && <>
              <Field label="Months of expenses to cover"><input type="number" min="1" max="24" value={inputs.months_target} onChange={set("months_target")} /></Field>
              <Field label={`Monthly expenses (${cur})`} help="Leave empty to use your last 3 months"><input type="number" min="0" value={inputs.monthly_expenses} onChange={set("monthly_expenses")} /></Field>
              <Field label={`Saved so far (${cur})`} help="Leave empty to use your savings and cash accounts"><input type="number" min="0" value={inputs.current_savings} onChange={set("current_savings")} /></Field>
            </>}
            <button className="btn" disabled={run.isPending || !code}>Calculate</button>
          </div>
          <ErrorNote error={run.error} />
        </form>
      </Card>

      {r && run.data && (
        <Card title="Result">
          <div className="stack">
            {(tab === "regular_investing" || tab === "compound_growth") && <>
              <div className="grid-3">
                <Stat label="Value at the end" value={money(r.final_value as string, cur, locale, { decimals: 0 })} />
                <Stat label="You put in" value={money((r.total_invested ?? r.total_contributed) as string, cur, locale, { decimals: 0 })} />
                <Stat label="Growth" value={money(r.total_growth as string, cur, locale, { decimals: 0 })} />
              </div>
              <GrowthChart series={r.series as Point[]} cur={cur} locale={locale} contributedLabel="You put in" />
            </>}
            {tab === "loan_repayment" && <>
              <div className="grid-3">
                <Stat label="Monthly repayment" value={money(r.monthly_payment as string, cur, locale)} />
                <Stat label="Total interest" value={money(r.total_interest as string, cur, locale, { decimals: 0 })} />
                <Stat label="Total repaid" value={money(r.total_paid as string, cur, locale, { decimals: 0 })} />
              </div>
              {r.with_extra ? (() => {
                const x = r.with_extra as Record<string, string | number>;
                return <div className="success">Paying {money(x.monthly_payment as string, cur, locale)} a month clears the loan {x.months_saved} months sooner and saves {money(x.interest_saved as string, cur, locale, { decimals: 0 })} in interest.</div>;
              })() : null}
            </>}
            {tab === "emergency_fund" && <>
              <div className="grid-3">
                <Stat label="Target" value={money(r.target as string, cur, locale, { decimals: 0 })} />
                <Stat label="Saved" value={money(r.current_savings as string, cur, locale, { decimals: 0 })} />
                <Stat label="Still to save" value={money(r.gap as string, cur, locale, { decimals: 0 })} />
              </div>
              <p className="muted">
                {r.months_covered !== null ? `Your savings cover about ${r.months_covered} months of expenses.` : "Add some spending first, or enter your monthly expenses."}{" "}
                Many people aim for 3 to 6 months.
              </p>
              {Object.values((r.sources ?? {}) as Record<string, string>).length > 0 && (
                <p className="small muted">Using: {Object.entries(r.sources as Record<string, string>).map(([k, v]) => `${k.replace("_", " ")}: ${v}`).join("; ")}</p>
              )}
            </>}
            <Disclaimer text={run.data.disclaimer} />
          </div>
        </Card>
      )}
      {!r && <Disclaimer text={ctx?.disclaimer} />}
    </>
  );
}

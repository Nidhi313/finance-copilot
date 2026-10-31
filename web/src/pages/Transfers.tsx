import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, call } from "../api";
import { Card, Empty, ErrorNote, Field, PageHead } from "../components/ui";
import { money, num, shortDate, today } from "../format";
import { useActiveCountry, useCountries, useMe } from "../hooks";

export default function Transfers() {
  const me = useMe();
  const qc = useQueryClient();
  const countries = useCountries();
  const { locale } = useActiveCountry();
  const home = me.data?.home_currency ?? "AUD";
  const links = me.data?.countries ?? [];
  const byCode = new Map((countries.data ?? []).map((c) => [c.code, c]));
  const [f, setF] = useState({
    date: today(), from_country_code: links[0]?.country_code ?? "", to_country_code: links[1]?.country_code ?? links[0]?.country_code ?? "",
    amount_sent: "", fee: "0", amount_received: "", provider: "",
  });
  const list = useQuery({ queryKey: ["remittances"], queryFn: () => call(api.GET("/v1/remittances")) });
  const summary = useQuery({
    queryKey: ["remittance-summary", home],
    queryFn: () => call(api.GET("/v1/remittances/summary", { params: { query: { currency: home } } })),
  });
  const add = useMutation({
    mutationFn: () => call(api.POST("/v1/remittances", { body: { ...f } })),
    onSuccess: () => { qc.invalidateQueries(); setF({ ...f, amount_sent: "", fee: "0", amount_received: "" }); },
  });
  const remove = useMutation({
    mutationFn: (id: string) => call(api.DELETE("/v1/remittances/{remittance_id}", { params: { path: { remittance_id: id } } })),
    onSuccess: () => qc.invalidateQueries(),
  });
  const fromCur = byCode.get(f.from_country_code)?.currency ?? "";
  const toCur = byCode.get(f.to_country_code)?.currency ?? "";
  const s = summary.data;

  return (
    <>
      <PageHead title="Money sent home" sub="Each transfer between your countries, and what it really cost: the fee you saw plus the margin hidden in the exchange rate." />
      {s && s.transfers_counted > 0 && (
        <div className="grid-3">
          <Card title="Total cost"><div className="big-number">{money(s.total_cost, home, locale)}</div>
            <p className="muted small">{s.cost_percent}% of the {money(s.sent, home, locale, { decimals: 0 })} you sent</p></Card>
          <Card title="Fees you saw"><div className="big-number">{money(s.fees, home, locale)}</div></Card>
          <Card title="Hidden in the rate"><div className="big-number">{money(s.rate_margin, home, locale)}</div>
            <p className="muted small">The difference between the provider's rate and the market rate that day</p></Card>
        </div>
      )}
      <Card title="Log a transfer">
        <form className="stack" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
          <div className="form">
            <Field label="Date"><input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} required /></Field>
            <Field label="From">
              <select value={f.from_country_code} onChange={(e) => setF({ ...f, from_country_code: e.target.value })}>
                {links.map((l) => <option key={l.country_code} value={l.country_code}>{byCode.get(l.country_code)?.name}</option>)}
              </select>
            </Field>
            <Field label="To">
              <select value={f.to_country_code} onChange={(e) => setF({ ...f, to_country_code: e.target.value })}>
                {links.map((l) => <option key={l.country_code} value={l.country_code}>{byCode.get(l.country_code)?.name}</option>)}
              </select>
            </Field>
            <Field label={`You paid in total (${fromCur})`} help="Including the fee">
              <input type="number" min="0" step="0.01" value={f.amount_sent} onChange={(e) => setF({ ...f, amount_sent: e.target.value })} required />
            </Field>
            <Field label={`Of which fee (${fromCur})`}>
              <input type="number" min="0" step="0.01" value={f.fee} onChange={(e) => setF({ ...f, fee: e.target.value })} />
            </Field>
            <Field label={`They received (${toCur})`}>
              <input type="number" min="0" step="0.01" value={f.amount_received} onChange={(e) => setF({ ...f, amount_received: e.target.value })} required />
            </Field>
            <Field label="Provider"><input value={f.provider} onChange={(e) => setF({ ...f, provider: e.target.value })} placeholder="Bank or transfer service" /></Field>
            <button className="btn" disabled={add.isPending}>Save transfer</button>
          </div>
          {links.length < 2 && <p className="small muted">Add a second country in Settings to log transfers between countries.</p>}
          <ErrorNote error={add.error} />
        </form>
      </Card>
      <Card title="Your transfers">
        <ErrorNote error={list.error} />
        {list.data?.length === 0 ? <Empty>No transfers logged yet.</Empty> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Date</th><th>Route</th><th>Provider</th><th className="num">Paid</th><th className="num">Received</th><th className="num">Your rate</th><th className="num">Market rate</th><th className="num">Total cost</th><th /></tr></thead>
              <tbody>
                {list.data?.map((r) => (
                  <tr key={r.id}>
                    <td>{shortDate(r.date, locale)}</td>
                    <td>{r.from_country_code} to {r.to_country_code}</td>
                    <td>{r.provider || <span className="muted">-</span>}</td>
                    <td className="num">{money(r.amount_sent, r.from_currency, locale)}</td>
                    <td className="num">{money(r.amount_received, r.to_currency, byCode.get(r.to_country_code)?.locale ?? locale)}</td>
                    <td className="num">{num(r.effective_rate).toFixed(4)}</td>
                    <td className="num">{r.market_rate ? num(r.market_rate).toFixed(4) : <span className="muted small">not available</span>}</td>
                    <td className="num">
                      {r.total_cost ? <>{money(r.total_cost, r.from_currency, locale)} <span className="small muted">({r.cost_percent}%)</span></> : "-"}
                    </td>
                    <td className="num"><button className="btn link" onClick={() => remove.mutate(r.id)}>Delete</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {s && s.transfers_without_market_rate > 0 && (
          <p className="small muted" style={{ marginTop: 10 }}>
            {s.transfers_without_market_rate} transfer(s) have no market rate for their date yet, so their cost is not counted.
          </p>
        )}
      </Card>
    </>
  );
}

import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, call } from "../api";
import { Card, Empty, ErrorNote, PageHead, Progress } from "../components/ui";
import { money, monthLabel, num } from "../format";
import { useActiveCountry, useCountries, useMe } from "../hooks";

const SPLIT_COLORS = ["#10282e", "#e3a008", "#3d7f8c", "#b5651d", "#7a8f3b", "#8c5e9e"];

export default function Overview() {
  const me = useMe();
  const { code, ctx, locale } = useActiveCountry();
  const countries = useCountries();
  const home = me.data?.home_currency ?? "AUD";
  const names = new Map((countries.data ?? []).map((c) => [c.code, c.name]));

  const worth = useQuery({
    queryKey: ["net-worth", home],
    queryFn: () => call(api.GET("/v1/reports/net-worth", { params: { query: { currency: home } } })),
  });
  const spending = useQuery({
    queryKey: ["spending", code],
    queryFn: () => call(api.GET("/v1/reports/spending", { params: { query: { country: code!, months: 6 } } })),
    enabled: !!code,
  });
  const budgets = useQuery({
    queryKey: ["budget-status", code, "current"],
    queryFn: () => call(api.GET("/v1/budgets/status", { params: { query: { country: code! } } })),
    enabled: !!code,
  });
  const transfers = useQuery({
    queryKey: ["remittance-summary", home],
    queryFn: () => call(api.GET("/v1/remittances/summary", { params: { query: { currency: home } } })),
  });

  const nw = worth.data;
  const total = num(nw?.total);
  const parts = Object.entries(nw?.by_country ?? {}).filter(([, v]) => num(v) > 0);
  const positiveTotal = parts.reduce((s, [, v]) => s + num(v), 0);
  const cur = spending.data?.currency ?? ctx?.currency ?? home;

  return (
    <>
      <PageHead title="Overview" sub={ctx ? `Spending and budgets are for ${ctx.name}. Net worth covers every country.` : undefined} />
      <ErrorNote error={worth.error} />

      <Card
        title="Net worth"
        sub={nw?.rates_as_of ? `Across all your countries, in ${home}. Exchange rates as of ${nw.rates_as_of}.` : `In ${home}`}
        action={<Link to="/accounts" className="btn secondary">Accounts</Link>}
      >
        <div className={`big-number ${total < 0 ? "neg" : ""}`}>{money(total, home, locale)}</div>
        {parts.length > 0 && (
          <>
            <div className="split" aria-hidden="true">
              {parts.map(([cc, v], i) => (
                <span key={cc} style={{ width: `${(num(v) / positiveTotal) * 100}%`, background: SPLIT_COLORS[i % SPLIT_COLORS.length] }} />
              ))}
            </div>
            <div className="legend">
              {parts.map(([cc, v], i) => (
                <span key={cc}>
                  <i style={{ background: SPLIT_COLORS[i % SPLIT_COLORS.length] }} />
                  {names.get(cc) ?? cc} {money(v, home, locale, { decimals: 0 })}
                </span>
              ))}
            </div>
          </>
        )}
        {nw && nw.accounts.length === 0 && <Empty>No accounts yet. <Link to="/accounts">Add your first account</Link>.</Empty>}
        {nw && nw.missing_rates.length > 0 && (
          <p className="small muted" style={{ marginTop: 10 }}>
            Not included yet: accounts in {nw.missing_rates.join(", ")}, because there is no exchange rate for them.
          </p>
        )}
      </Card>

      <div className="grid-2">
        <Card title="This month's spending" sub={ctx?.name}>
          {spending.data && spending.data.by_category.length === 0 && <Empty>No spending recorded this month.</Empty>}
          <div className="stack">
            {spending.data?.by_category.slice(0, 7).map((c) => (
              <div key={String(c.category)}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span>{String(c.category)}</span>
                  <span>{money(c.amount as string, cur, locale)}</span>
                </div>
                <Progress percent={num(c.percent as string)} />
              </div>
            ))}
          </div>
          {spending.data && num(spending.data.spending) > 0 && (
            <p className="small muted" style={{ marginTop: 12 }}>
              Total {money(spending.data.spending, cur, locale)} · income {money(spending.data.income, cur, locale)}
            </p>
          )}
        </Card>

        <Card title="Budgets" sub="This month" action={<Link to="/budgets" className="btn secondary">Manage</Link>}>
          {budgets.data?.length === 0 && <Empty>No budgets for {ctx?.name ?? "this country"} yet.</Empty>}
          <div className="stack">
            {budgets.data?.slice(0, 5).map((b) => (
              <div key={b.budget_id}>
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <span>{b.category}</span>
                  <span className="small">
                    {money(b.spent, b.currency, locale, { decimals: 0 })} of {money(b.budget, b.currency, locale, { decimals: 0 })}
                  </span>
                </div>
                <Progress percent={num(b.percent_used)} />
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid-2">
        <Card title="Income and spending" sub={`Last 6 months, ${cur}`}>
          {spending.data && (
            <div style={{ width: "100%", height: 240 }}>
              <ResponsiveContainer>
                <BarChart data={spending.data.monthly.map((m) => ({
                  month: monthLabel(String(m.month), locale), Income: num(m.income as string), Spending: num(m.spending as string),
                }))}>
                  <CartesianGrid vertical={false} stroke="#eaefed" />
                  <XAxis dataKey="month" tickLine={false} axisLine={false} fontSize={12} />
                  <YAxis tickLine={false} axisLine={false} fontSize={12} width={60}
                    tickFormatter={(v) => money(v, cur, locale, { decimals: 0 })} />
                  <Tooltip formatter={(v: number) => money(v, cur, locale)} />
                  <Legend iconType="square" />
                  <Bar dataKey="Income" fill="#3d7f8c" radius={[3, 3, 0, 0]} />
                  <Bar dataKey="Spending" fill="#10282e" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card title="Money sent home" sub="What your transfers really cost" action={<Link to="/transfers" className="btn secondary">Transfers</Link>}>
          {transfers.data && transfers.data.transfers_counted === 0 ? (
            <Empty>Log a transfer to see the fee and the hidden exchange-rate margin you paid.</Empty>
          ) : (
            transfers.data && (
              <div className="stack">
                <div className="big-number">{money(transfers.data.total_cost, home, locale)}</div>
                <p className="muted">
                  Total cost across {transfers.data.transfers_counted} transfer{transfers.data.transfers_counted === 1 ? "" : "s"}
                  {transfers.data.cost_percent ? ` (${transfers.data.cost_percent}% of what you sent)` : ""}.{" "}
                  Fees {money(transfers.data.fees, home, locale)}, exchange-rate margin {money(transfers.data.rate_margin, home, locale)}.
                </p>
              </div>
            )
          )}
        </Card>
      </div>
    </>
  );
}

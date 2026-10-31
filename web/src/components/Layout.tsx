import { useMutation, useQueryClient } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";
import { api, call } from "../api";
import { keys, useCountries, useMe } from "../hooks";

const NAV = [
  { group: "Track", links: [
    ["/", "Overview"], ["/accounts", "Accounts"], ["/transactions", "Transactions"],
    ["/budgets", "Budgets"], ["/transfers", "Money sent home"], ["/goals", "Goals"],
  ] },
  { group: "Plan", links: [["/plan", "Calculators"]] },
  { group: "You", links: [["/settings", "Countries and settings"]] },
];

export function CountrySwitcher() {
  const me = useMe();
  const countries = useCountries();
  const qc = useQueryClient();
  const setActive = useMutation({
    mutationFn: (code: string) => call(api.PATCH("/v1/me", { body: { active_country_code: code } })),
    onSuccess: (data) => qc.setQueryData(keys.me, data),
  });
  const byCode = new Map((countries.data ?? []).map((c) => [c.code, c]));
  const links = me.data?.countries ?? [];
  if (!links.length) return null;
  return (
    <div className="switcher" role="group" aria-label="Country">
      <span className="switcher-label">Viewing</span>
      {links.map((l) => {
        const c = byCode.get(l.country_code);
        return (
          <button
            key={l.country_code}
            className="country-pill"
            aria-pressed={me.data?.active_country_code === l.country_code}
            onClick={() => setActive.mutate(l.country_code)}
          >
            {c?.name ?? l.country_code}
            <span className="cur">{c?.currency}</span>
          </button>
        );
      })}
    </div>
  );
}

export function Layout() {
  const me = useMe();
  return (
    <div className="shell">
      <nav className="side" aria-label="Main">
        <div className="brand">Finance Copilot</div>
        {NAV.map((g) => (
          <div className="nav-group" key={g.group}>
            <div className="nav-label">{g.group}</div>
            {g.links.map(([to, label]) => (
              <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}>
                {label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className="main">
        <header className="topbar">
          <CountrySwitcher />
          <span className="spacer" />
          {me.data && <span className="hint">Home currency: {me.data.home_currency}</span>}
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, call } from "../api";
import { keys } from "../hooks";
import { Card, Progress } from "./ui";

const STEPS: Record<string, { title: string; why: string; to: string; cta: string }> = {
  countries: { title: "Add the countries you live and bank in", why: "Every screen can switch between them.", to: "/settings", cta: "Add countries" },
  account: { title: "Add your first account", why: "A bank account, savings, super, PPF: anything with a balance.", to: "/accounts", cta: "Add an account" },
  transactions: { title: "Import a statement or add a transaction", why: "Download a CSV from your bank and import it. Re-importing never duplicates.", to: "/transactions", cta: "Go to transactions" },
  budget: { title: "Set a monthly budget", why: "Pick a category like Groceries and a monthly limit.", to: "/budgets", cta: "Set a budget" },
  transfer: { title: "Log money you sent home", why: "See the fee plus the margin hidden in the exchange rate.", to: "/transfers", cta: "Log a transfer" },
  goal: { title: "Set a savings goal", why: "A trip home, a deposit, a buffer. Link an account to track it.", to: "/goals", cta: "Add a goal" },
};

export function GettingStarted() {
  const qc = useQueryClient();
  const gs = useQuery({ queryKey: ["getting-started"], queryFn: () => call(api.GET("/v1/me/getting-started")) });
  const hide = useMutation({
    mutationFn: () => call(api.PATCH("/v1/me", { body: { onboarding_dismissed: true } })),
    onSuccess: (d) => {
      qc.setQueryData(keys.me, d);
      qc.invalidateQueries({ queryKey: ["getting-started"] });
    },
  });
  const data = gs.data;
  if (!data || data.dismissed) return null;
  const allDone = data.done_count === data.total;
  const next = data.steps.find((s) => !s.done);

  return (
    <Card
      title={allDone ? "You're all set up" : "Getting started"}
      sub={allDone ? "Everything below now updates from your own data." : `${data.done_count} of ${data.total} done`}
      action={<button className="btn link" onClick={() => hide.mutate()}>{allDone ? "Close" : "Hide this"}</button>}
    >
      <Progress percent={(data.done_count / data.total) * 100} />
      <ol className="checklist">
        {data.steps.map((s) => {
          const step = STEPS[s.key];
          const isNext = next?.key === s.key;
          return (
            <li key={s.key} className={s.done ? "done" : isNext ? "next" : ""}>
              <span className="tick" aria-hidden="true">{s.done ? "✓" : ""}</span>
              <div>
                <div className="checklist-title">{step.title}</div>
                {!s.done && <div className="small muted">{step.why}</div>}
              </div>
              {!s.done && (
                <Link to={step.to} className={isNext ? "btn" : "btn secondary"}>{step.cta}</Link>
              )}
              <span className="sr-only">{s.done ? "Done" : "Not done"}</span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

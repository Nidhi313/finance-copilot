import { useState } from "react";
import { signIn } from "../auth";
import { ErrorNote } from "../components/ui";

export default function SignIn({ problem }: { problem?: string | null }) {
  const [error, setError] = useState<unknown>(null);
  return (
    <main className="signin">
      <div className="signin-card stack">
        <div className="brand-dark">Finance Copilot</div>
        <h1>Your money, across every country you live in</h1>
        <p className="muted">
          Track accounts in each country in one place, see your net worth in one currency, find out what your
          transfers home really cost, and plan with simple calculators.
        </p>
        <ul className="signin-points">
          <li>Your data is private to your account.</li>
          <li>Information and simulations only, never financial advice.</li>
          <li>Australia and India have local detail; every other country works too.</li>
        </ul>
        <ErrorNote error={problem ? new Error(problem) : error} />
        <div>
          <button className="btn" disabled={!!problem} onClick={() => signIn().catch(setError)}>
            Sign in or create an account
          </button>
        </div>
        <p className="small muted">New here? Choose "Sign up" on the next screen. It takes a minute.</p>
      </div>
    </main>
  );
}

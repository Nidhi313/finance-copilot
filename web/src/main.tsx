import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ErrorNote } from "./components/ui";
import { useMe } from "./hooks";
import Accounts from "./pages/Accounts";
import Budgets from "./pages/Budgets";
import Goals from "./pages/Goals";
import Onboarding from "./pages/Onboarding";
import Overview from "./pages/Overview";
import Plan from "./pages/Plan";
import Settings from "./pages/Settings";
import Transactions from "./pages/Transactions";
import Transfers from "./pages/Transfers";
import "./styles.css";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

function App() {
  const me = useMe();
  if (me.isLoading) return <div className="content">Loading…</div>;
  if (me.error)
    return (
      <div className="content">
        <ErrorNote error={new Error(`Cannot reach the API. Is it running? (${me.error.message})`)} />
      </div>
    );
  if (!me.data?.countries.length) return <Onboarding />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="accounts" element={<Accounts />} />
        <Route path="transactions" element={<Transactions />} />
        <Route path="budgets" element={<Budgets />} />
        <Route path="transfers" element={<Transfers />} />
        <Route path="goals" element={<Goals />} />
        <Route path="plan" element={<Plan />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);

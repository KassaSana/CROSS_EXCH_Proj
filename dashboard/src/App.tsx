import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Nav } from "./components/Nav";
import Dashboard from "./pages/Dashboard";

const Statistics = lazy(() => import("./pages/Statistics"));

export default function App() {
  return (
    <BrowserRouter>
      <main className="min-h-screen bg-canvas px-4 py-8 text-ink">
        <div className="mx-auto max-w-7xl">
          <header className="mb-8 rounded-[2rem] border border-stone-300 bg-gradient-to-r from-white to-amber-50 p-8 shadow-sm">
            <p className="text-xs uppercase tracking-[0.35em] text-stone-500">Portfolio System Design Build</p>
            <h1 className="mt-3 font-display text-5xl leading-tight">Cross-Exchange Arbitrage Detector</h1>
            <p className="mt-4 max-w-3xl text-stone-600">
              Event-driven market data ingestion, in-memory book maintenance, theoretical arbitrage detection, and live streaming observability.
            </p>
          </header>

          <Nav />

          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route
              path="/stats"
              element={
                <Suspense fallback={<p className="p-8 text-stone-500">Loading statistics...</p>}>
                  <Statistics />
                </Suspense>
              }
            />
          </Routes>
        </div>
      </main>
    </BrowserRouter>
  );
}

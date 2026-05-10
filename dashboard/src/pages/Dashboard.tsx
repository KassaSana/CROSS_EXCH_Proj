import { useEffect, useState } from "react";
import {
  AdapterStatus,
  fetchAdapterStatus,
  fetchPairs,
  fetchRecentOpportunities,
  fetchStats,
  Opportunity,
  PairRecord,
  Stats,
  TopOfBook,
} from "../api/client";
import { AdapterStatusBanner } from "../components/AdapterStatus";
import { LiveSpreads } from "../components/LiveSpreads";
import { OpportunityFeed } from "../components/OpportunityFeed";
import { StatsCards } from "../components/StatsCards";
import { useWebSocket } from "../hooks/useWebSocket";

type LivePayload =
  | { type: "top_of_book"; payload: TopOfBook }
  | { type: "opportunity"; payload: Opportunity };

export default function Dashboard() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [pairs, setPairs] = useState<PairRecord[]>([]);
  const [books, setBooks] = useState<Record<string, TopOfBook>>({});
  const [adapters, setAdapters] = useState<AdapterStatus[]>([]);

  useEffect(() => {
    fetchRecentOpportunities().then(setOpportunities);
    fetchStats().then(setStats);
    fetchPairs().then(setPairs);
    const pollAdapterStatus = () => {
      fetchAdapterStatus().then(setAdapters).catch(() => setAdapters([]));
    };
    pollAdapterStatus();
    const interval = window.setInterval(pollAdapterStatus, 2000);
    return () => window.clearInterval(interval);
  }, []);

  useWebSocket((event) => {
    const message = JSON.parse(event.data) as LivePayload;
    if (message.type === "opportunity") {
      setOpportunities((current) => [message.payload, ...current].slice(0, 50));
    }
    if (message.type === "top_of_book") {
      setBooks((current) => ({
        ...current,
        [`${message.payload.exchange}:${message.payload.pair}`]: message.payload,
      }));
    }
  });

  return (
    <div className="space-y-6">
      <AdapterStatusBanner adapters={adapters} />
      <StatsCards stats={stats} />
      <LiveSpreads pairs={pairs} books={books} />
      <OpportunityFeed opportunities={opportunities} />
    </div>
  );
}

import { useEffect, useState } from "react";
import {
  AdapterStatus,
  BookStatus,
  fetchAdapterStatus,
  fetchBookStatus,
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
  | { type: "opportunity"; payload: Opportunity }
  | { type: "book_status"; payload: BookStatus };

export default function Dashboard() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [pairs, setPairs] = useState<PairRecord[]>([]);
  const [books, setBooks] = useState<Record<string, TopOfBook>>({});
  const [adapters, setAdapters] = useState<AdapterStatus[]>([]);
  const [bookStatuses, setBookStatuses] = useState<Record<string, BookStatus>>({});

  useEffect(() => {
    fetchRecentOpportunities().then(setOpportunities);
    fetchStats().then(setStats);
    fetchPairs().then(setPairs);
    const pollAdapterStatus = () => {
      fetchAdapterStatus().then(setAdapters).catch(() => setAdapters([]));
      fetchBookStatus()
        .then((statuses) => {
          setBookStatuses(Object.fromEntries(
            statuses.map((status) => [`${status.exchange}:${status.pair}`, status]),
          ));
          setBooks((current) => Object.fromEntries(
            Object.entries(current).filter(([key]) => statuses.some(
              (status) => `${status.exchange}:${status.pair}` === key && status.eligible,
            )),
          ));
        })
        .catch(() => setBookStatuses({}));
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
    if (message.type === "book_status") {
      const key = `${message.payload.exchange}:${message.payload.pair}`;
      setBookStatuses((current) => ({ ...current, [key]: message.payload }));
      if (!message.payload.eligible) {
        setBooks((current) => Object.fromEntries(
          Object.entries(current).filter(([bookKey]) => bookKey !== key),
        ));
      }
    }
  });

  return (
    <div className="space-y-6">
      <AdapterStatusBanner adapters={adapters} books={bookStatuses} />
      <StatsCards stats={stats} />
      <LiveSpreads pairs={pairs} books={books} />
      <OpportunityFeed opportunities={opportunities} />
    </div>
  );
}

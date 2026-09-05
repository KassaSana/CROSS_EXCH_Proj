import { useEffect, useRef, useState } from "react";
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
  | { type: "book_status"; payload: BookStatus }
  | {
      type: "state_snapshot";
      payload: { books: TopOfBook[]; statuses: BookStatus[] };
    };

type LiveEnvelope = LivePayload & { stream_sequence: number };

function opportunityKey(opportunity: Opportunity): string {
  return [
    opportunity.timestamp_ns,
    opportunity.pair,
    opportunity.buy_exchange,
    opportunity.sell_exchange,
  ].join(":");
}

function mergeOpportunities(current: Opportunity[], fetched: Opportunity[]): Opportunity[] {
  const unique = new Map<string, Opportunity>();
  for (const opportunity of [...current, ...fetched]) {
    unique.set(opportunityKey(opportunity), opportunity);
  }
  return [...unique.values()]
    .sort((left, right) => right.timestamp_ns - left.timestamp_ns)
    .slice(0, 50);
}

export default function Dashboard() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [pairs, setPairs] = useState<PairRecord[]>([]);
  const [books, setBooks] = useState<Record<string, TopOfBook>>({});
  const [adapters, setAdapters] = useState<AdapterStatus[]>([]);
  const [bookStatuses, setBookStatuses] = useState<Record<string, BookStatus>>({});

  useEffect(() => {
    fetchRecentOpportunities().then((fetched) => {
      setOpportunities((current) => mergeOpportunities(current, fetched));
    });
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

  const lastStreamMessage = useRef({ connectionId: 0, sequence: 0 });
  const websocket = useWebSocket((event, connectionId) => {
    const message = JSON.parse(event.data) as LiveEnvelope;
    if (lastStreamMessage.current.connectionId !== connectionId) {
      lastStreamMessage.current = { connectionId, sequence: 0 };
    }
    if (message.stream_sequence <= lastStreamMessage.current.sequence) {
      return;
    }
    lastStreamMessage.current.sequence = message.stream_sequence;

    if (message.type === "state_snapshot") {
      setBooks(Object.fromEntries(
        message.payload.books.map((book) => [`${book.exchange}:${book.pair}`, book]),
      ));
      setBookStatuses(Object.fromEntries(
        message.payload.statuses.map((status) => [
          `${status.exchange}:${status.pair}`,
          status,
        ]),
      ));
    }
    if (message.type === "opportunity") {
      setOpportunities((current) => mergeOpportunities([message.payload], current));
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

  useEffect(() => {
    if (websocket.status === "connected") {
      fetchRecentOpportunities()
        .then((fetched) => {
          setOpportunities((current) => mergeOpportunities(current, fetched));
        })
        .catch(() => undefined);
      fetchStats().then(setStats).catch(() => undefined);
    }
  }, [websocket.connectionId, websocket.status]);

  const displayedBooks = websocket.status === "connected" ? books : {};
  const displayedBookStatuses = websocket.status === "connected"
    ? bookStatuses
    : Object.fromEntries(
        Object.entries(bookStatuses).map(([key, status]) => [
          key,
          { ...status, connected: false, eligible: false, reason: "disconnected" },
        ]),
      );

  return (
    <div className="space-y-6">
      <AdapterStatusBanner
        adapters={adapters}
        books={displayedBookStatuses}
        connectionStatus={websocket.status}
      />
      <StatsCards stats={stats} />
      <LiveSpreads pairs={pairs} books={displayedBooks} />
      <OpportunityFeed opportunities={opportunities} />
    </div>
  );
}

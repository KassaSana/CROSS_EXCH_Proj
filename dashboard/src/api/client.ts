export type Opportunity = {
  timestamp_ns: number;
  pair: string;
  buy_exchange: string;
  sell_exchange: string;
  buy_price: string;
  sell_price: string;
  spread_pct: string;
  max_size: string;
  theoretical_profit_usd: string;
};

export type PairRecord = {
  exchange: string;
  pair: string;
};

export type Stats = {
  count: number;
  max_spread_pct: string;
  total_theoretical_profit_usd: string;
};

export type AdapterStatus = {
  exchange: string;
  connected: boolean;
  last_message_age_ms: number | null;
  gap_count: number;
  reconnect_count: number;
  last_error: string | null;
};

export type BookStatus = {
  exchange: string;
  pair: string;
  initialized: boolean;
  continuous: boolean;
  connected: boolean;
  age_ms: number | null;
  max_age_ms: number;
  eligible: boolean;
  reason: string | null;
};

export type TopOfBook = {
  exchange: string;
  pair: string;
  best_bid_price: string;
  best_bid_size: string;
  best_ask_price: string;
  best_ask_size: string;
  sequence: number;
  timestamp_ns: number;
};

export type WindowKey = "1h" | "4h" | "1d" | "1w";

export type PeakMinute = {
  minute_start_ns: number;
  count: number;
};

export type SystemOverview = {
  started_at_ns: number;
  uptime_seconds: number;
  all_time_count: number;
  all_time_max_spread_pct: string;
  all_time_peak_minute: PeakMinute | null;
};

export type WindowStats = {
  window: string;
  count: number;
  max_spread_pct: string;
  mean_spread_pct: string;
  total_theoretical_profit_usd: string;
  top_pair: string | null;
  peak_minute: PeakMinute | null;
};

export type TimeseriesPoint = {
  bucket_start_ns: number;
  count: number;
  max_spread_pct: string;
};

export type Timeseries = {
  window: string;
  bucket_seconds: number;
  points: TimeseriesPoint[];
};

const API_BASE = import.meta.env.VITE_API_URL ?? "https://arb-detector-api.onrender.com";
const WS_BASE = API_BASE.replace(/^http/, "ws");

export { WS_BASE };

export async function fetchRecentOpportunities(): Promise<Opportunity[]> {
  const response = await fetch(`${API_BASE}/api/opportunities/recent?limit=50`);
  return response.json();
}

export async function fetchStats(): Promise<Stats> {
  const response = await fetch(`${API_BASE}/api/stats?window=1h`);
  return response.json();
}

export async function fetchPairs(): Promise<PairRecord[]> {
  const response = await fetch(`${API_BASE}/api/pairs`);
  return response.json();
}

export async function fetchAdapterStatus(): Promise<AdapterStatus[]> {
  const response = await fetch(`${API_BASE}/api/adapters`);
  return response.json();
}

export async function fetchBookStatus(): Promise<BookStatus[]> {
  const response = await fetch(`${API_BASE}/api/book-status`);
  return response.json();
}

export async function fetchSystemOverview(): Promise<SystemOverview> {
  const response = await fetch(`${API_BASE}/api/system/overview`);
  return response.json();
}

export async function fetchSystemStats(window: WindowKey): Promise<WindowStats> {
  const response = await fetch(`${API_BASE}/api/system/stats?window=${window}`);
  return response.json();
}

export async function fetchSystemTimeseries(
  window: WindowKey,
  bucketSeconds = 60,
): Promise<Timeseries> {
  const response = await fetch(
    `${API_BASE}/api/system/timeseries?window=${window}&bucket_seconds=${bucketSeconds}`,
  );
  return response.json();
}

export async function resetSystemTimer(): Promise<{ started_at_ns: number; uptime_seconds: number }> {
  const response = await fetch(`${API_BASE}/api/system/reset`, { method: "POST" });
  return response.json();
}

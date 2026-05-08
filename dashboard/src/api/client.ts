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

export async function fetchRecentOpportunities(): Promise<Opportunity[]> {
  const response = await fetch("/api/opportunities/recent?limit=50");
  return response.json();
}

export async function fetchStats(): Promise<Stats> {
  const response = await fetch("/api/stats?window=1h");
  return response.json();
}

export async function fetchPairs(): Promise<PairRecord[]> {
  const response = await fetch("/api/pairs");
  return response.json();
}

export async function fetchAdapterStatus(): Promise<AdapterStatus[]> {
  const response = await fetch("/api/adapters");
  return response.json();
}

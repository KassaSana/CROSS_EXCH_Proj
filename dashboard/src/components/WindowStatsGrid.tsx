import { WindowStats } from "../api/client";

type Props = {
  stats: WindowStats | null;
};

function formatPercent(value: string | undefined): string {
  if (value === undefined) return "—";
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "—";
  return `${n.toFixed(3)}%`;
}

function formatUsd(value: string | undefined): string {
  if (value === undefined) return "—";
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function formatPeak(stats: WindowStats | null): { value: string; sub: string } {
  if (!stats || !stats.peak_minute) return { value: "—", sub: "Insufficient data" };
  const date = new Date(Math.floor(stats.peak_minute.minute_start_ns / 1_000_000));
  return {
    value: `${stats.peak_minute.count} opps`,
    sub: date.toLocaleString(),
  };
}

export function WindowStatsGrid({ stats }: Props) {
  const isEmpty = !stats || stats.count === 0;
  const peak = formatPeak(stats);

  if (isEmpty) {
    return (
      <section className="rounded-[2rem] border border-dashed border-stone-300 bg-stone-50 p-8 text-center text-stone-500 shadow-sm">
        <p className="text-xs uppercase tracking-[0.25em]">No opportunities in this window yet</p>
        <p className="mt-2 text-sm">Stats will populate as the system continues running.</p>
      </section>
    );
  }

  const items = [
    { label: "Opportunities", value: stats.count.toLocaleString(), sub: undefined },
    { label: "Top Pair", value: stats.top_pair ?? "—", sub: undefined },
    { label: "Max Spread", value: formatPercent(stats.max_spread_pct), sub: undefined },
    { label: "Mean Spread", value: formatPercent(stats.mean_spread_pct), sub: undefined },
    { label: "Theoretical Profit", value: formatUsd(stats.total_theoretical_profit_usd), sub: undefined },
    { label: "Peak Minute", value: peak.value, sub: peak.sub },
  ];

  return (
    <section className="grid gap-4 md:grid-cols-3">
      {items.map((item) => (
        <article key={item.label} className="rounded-3xl border border-stone-300 bg-white/80 p-5 shadow-sm">
          <p className="text-xs uppercase tracking-[0.2em] text-stone-500">{item.label}</p>
          <p className="mt-3 font-display text-3xl text-ink tabular-nums">{item.value}</p>
          {item.sub ? <p className="mt-1 text-xs text-stone-500">{item.sub}</p> : null}
        </article>
      ))}
    </section>
  );
}

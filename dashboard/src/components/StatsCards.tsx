import { Stats } from "../api/client";

type Props = {
  stats: Stats | null;
};

export function StatsCards({ stats }: Props) {
  const items = [
    { label: "Opportunities / Hour", value: stats?.count ?? "..." },
    { label: "Max Spread %", value: stats?.max_spread_pct ?? "..." },
    { label: "Theoretical Profit", value: stats ? `$${stats.total_theoretical_profit_usd}` : "..." },
  ];

  return (
    <section className="grid gap-4 md:grid-cols-3">
      {items.map((item) => (
        <article key={item.label} className="rounded-3xl border border-stone-300 bg-white/70 p-5 shadow-sm">
          <p className="text-xs uppercase tracking-[0.2em] text-stone-500">{item.label}</p>
          <p className="mt-3 font-display text-3xl text-ink">{item.value}</p>
        </article>
      ))}
    </section>
  );
}

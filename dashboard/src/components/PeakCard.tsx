import { PeakMinute } from "../api/client";

type Props = {
  allTimeCount: number;
  allTimeMaxSpread: string;
  allTimePeakMinute: PeakMinute | null;
};

function formatMinute(ns: number): string {
  return new Date(Math.floor(ns / 1_000_000)).toLocaleString();
}

export function PeakCard({ allTimeCount, allTimeMaxSpread, allTimePeakMinute }: Props) {
  const peakLabel = allTimePeakMinute ? `${allTimePeakMinute.count} opps` : "—";
  const peakWhen = allTimePeakMinute ? formatMinute(allTimePeakMinute.minute_start_ns) : "Insufficient data";
  const maxSpreadLabel = Number(allTimeMaxSpread) > 0 ? `${Number(allTimeMaxSpread).toFixed(3)}%` : "—";

  return (
    <section className="rounded-[2rem] border border-stone-300 bg-white/80 p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-stone-500">All-Time Peaks</p>
          <h2 className="mt-2 font-display text-2xl text-ink">Best moments observed</h2>
        </div>
        <p className="text-sm text-stone-500">Across the full opportunity history</p>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-3">
        <article className="rounded-3xl border border-stone-200 bg-stone-50 p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-stone-500">Total Opportunities</p>
          <p className="mt-3 font-display text-3xl text-ink tabular-nums">{allTimeCount.toLocaleString()}</p>
        </article>
        <article className="rounded-3xl border border-stone-200 bg-stone-50 p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-stone-500">Biggest Spread Ever</p>
          <p className="mt-3 font-display text-3xl text-ink tabular-nums">{maxSpreadLabel}</p>
        </article>
        <article className="rounded-3xl border border-stone-200 bg-stone-50 p-4">
          <p className="text-xs uppercase tracking-[0.2em] text-stone-500">Busiest Minute</p>
          <p className="mt-3 font-display text-3xl text-ink tabular-nums">{peakLabel}</p>
          <p className="mt-1 text-xs text-stone-500">{peakWhen}</p>
        </article>
      </div>
    </section>
  );
}

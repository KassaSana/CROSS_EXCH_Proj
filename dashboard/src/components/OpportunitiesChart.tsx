import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Timeseries, WindowKey } from "../api/client";

type Props = {
  data: Timeseries | null;
  window: WindowKey;
};

function formatTick(ns: string, window: WindowKey): string {
  const d = new Date(Number(BigInt(ns) / 1_000_000n));
  if (window === "1h" || window === "4h") {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function OpportunitiesChart({ data, window }: Props) {
  const points = data?.points ?? [];
  const allZero = points.every((p) => p.count === 0);

  if (points.length === 0 || allZero) {
    return (
      <section className="rounded-[2rem] border border-dashed border-stone-300 bg-stone-50 p-8 text-center text-stone-500 shadow-sm">
        <p className="text-xs uppercase tracking-[0.25em]">No timeseries data yet</p>
        <p className="mt-2 text-sm">The chart will render once opportunities accumulate.</p>
      </section>
    );
  }

  const chartData = points.map((p) => ({
    bucket: p.bucket_start_ns,
    count: p.count,
    label: formatTick(p.bucket_start_ns, window),
  }));

  return (
    <section className="rounded-[2rem] border border-stone-300 bg-white/80 p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-stone-500">Opportunities Over Time</p>
          <h2 className="mt-2 font-display text-2xl text-ink">Activity ({window})</h2>
        </div>
        <p className="text-sm text-stone-500">{points.length} buckets</p>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="opps" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#78716c" stopOpacity={0.6} />
                <stop offset="95%" stopColor="#78716c" stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#e7e5e4" />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#78716c" }} stroke="#d6d3d1" />
            <YAxis tick={{ fontSize: 11, fill: "#78716c" }} stroke="#d6d3d1" allowDecimals={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: "rgba(255,255,255,0.95)",
                border: "1px solid #d6d3d1",
                borderRadius: "0.75rem",
                fontSize: 12,
              }}
              labelStyle={{ color: "#44403c" }}
            />
            <Area type="monotone" dataKey="count" stroke="#44403c" strokeWidth={2} fill="url(#opps)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

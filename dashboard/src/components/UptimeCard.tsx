import { useEffect, useState } from "react";

type Props = {
  startedAtNs: number | null;
  onReset: () => void;
};

function formatUptime(seconds: number): string {
  if (seconds < 0) return "0s";
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  const secs = seconds % 60;
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m ${secs}s`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
}

export function UptimeCard({ startedAtNs, onReset }: Props) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const uptimeSeconds =
    startedAtNs === null ? 0 : Math.max(0, Math.floor((now * 1_000_000 - startedAtNs) / 1_000_000_000));
  const startedDisplay =
    startedAtNs === null ? "—" : new Date(Math.floor(startedAtNs / 1_000_000)).toLocaleString();

  return (
    <section className="rounded-[2rem] border border-stone-300 bg-gradient-to-r from-white to-amber-50 p-8 shadow-sm">
      <div className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.35em] text-stone-500">System Uptime</p>
          <p className="mt-3 font-display text-5xl text-ink tabular-nums">{formatUptime(uptimeSeconds)}</p>
          <p className="mt-2 text-sm text-stone-500">Running since {startedDisplay}</p>
        </div>
        <button
          type="button"
          onClick={onReset}
          className="self-start rounded-2xl border border-stone-300 bg-white/80 px-5 py-2 text-sm uppercase tracking-[0.25em] text-stone-700 transition-colors hover:bg-white md:self-auto"
        >
          Reset Timer
        </button>
      </div>
    </section>
  );
}

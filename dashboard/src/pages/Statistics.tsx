import { useCallback, useEffect, useState } from "react";
import {
  fetchSystemOverview,
  fetchSystemStats,
  fetchSystemTimeseries,
  resetSystemTimer,
  SystemOverview,
  Timeseries,
  WindowKey,
  WindowStats,
} from "../api/client";
import { OpportunitiesChart } from "../components/OpportunitiesChart";
import { PeakCard } from "../components/PeakCard";
import { UptimeCard } from "../components/UptimeCard";
import { WindowStatsGrid } from "../components/WindowStatsGrid";

const WINDOWS: { key: WindowKey; label: string; bucketSeconds: number }[] = [
  { key: "1h", label: "1 hour", bucketSeconds: 60 },
  { key: "4h", label: "4 hours", bucketSeconds: 240 },
  { key: "1d", label: "1 day", bucketSeconds: 900 },
  { key: "1w", label: "1 week", bucketSeconds: 3600 },
];

const POLL_MS = 5000;

export default function Statistics() {
  const [overview, setOverview] = useState<SystemOverview | null>(null);
  const [stats, setStats] = useState<WindowStats | null>(null);
  const [timeseries, setTimeseries] = useState<Timeseries | null>(null);
  const [windowKey, setWindowKey] = useState<WindowKey>("1h");
  const [confirmOpen, setConfirmOpen] = useState(false);

  const refresh = useCallback(async (key: WindowKey) => {
    const window = WINDOWS.find((w) => w.key === key) ?? WINDOWS[0];
    const [ov, st, ts] = await Promise.all([
      fetchSystemOverview().catch(() => null),
      fetchSystemStats(window.key).catch(() => null),
      fetchSystemTimeseries(window.key, window.bucketSeconds).catch(() => null),
    ]);
    setOverview(ov);
    setStats(st);
    setTimeseries(ts);
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- polling pattern: refresh fetches and updates state asynchronously
    void refresh(windowKey);
    const id = window.setInterval(() => void refresh(windowKey), POLL_MS);
    return () => window.clearInterval(id);
  }, [windowKey, refresh]);

  const handleResetConfirmed = async () => {
    setConfirmOpen(false);
    try {
      const result = await resetSystemTimer();
      setOverview((current) =>
        current
          ? { ...current, started_at_ns: result.started_at_ns, uptime_seconds: 0 }
          : current,
      );
    } catch {
      // Ignore: next poll will recover
    }
  };

  return (
    <div className="space-y-6">
      <UptimeCard
        startedAtNs={overview?.started_at_ns ?? null}
        onReset={() => setConfirmOpen(true)}
      />

      <PeakCard
        allTimeCount={overview?.all_time_count ?? 0}
        allTimeMaxSpread={overview?.all_time_max_spread_pct ?? "0"}
        allTimePeakMinute={overview?.all_time_peak_minute ?? null}
      />

      <section className="rounded-[2rem] border border-stone-300 bg-white/80 p-6 shadow-sm">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-stone-500">Window</p>
            <h2 className="mt-2 font-display text-2xl text-ink">Stats over time</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {WINDOWS.map((w) => {
              const active = w.key === windowKey;
              return (
                <button
                  key={w.key}
                  type="button"
                  onClick={() => setWindowKey(w.key)}
                  className={[
                    "rounded-2xl px-4 py-2 text-xs uppercase tracking-[0.25em] transition-colors",
                    active
                      ? "bg-ink text-white"
                      : "border border-stone-300 bg-white text-stone-600 hover:bg-stone-50",
                  ].join(" ")}
                >
                  {w.label}
                </button>
              );
            })}
          </div>
        </div>
      </section>

      <WindowStatsGrid stats={stats} />
      <OpportunitiesChart data={timeseries} window={windowKey} />

      {confirmOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-stone-900/40 px-4">
          <div className="w-full max-w-md rounded-[2rem] border border-stone-300 bg-white p-6 shadow-lg">
            <p className="text-xs uppercase tracking-[0.25em] text-stone-500">Confirm reset</p>
            <h3 className="mt-2 font-display text-2xl text-ink">Reset uptime counter?</h3>
            <p className="mt-3 text-sm text-stone-600">
              This resets the displayed uptime to zero. Your historical opportunity data is
              preserved — windowed stats and peaks will continue to reflect real history.
            </p>
            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                className="rounded-2xl border border-stone-300 bg-white px-4 py-2 text-sm uppercase tracking-[0.2em] text-stone-700 hover:bg-stone-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleResetConfirmed()}
                className="rounded-2xl bg-ink px-4 py-2 text-sm uppercase tracking-[0.2em] text-white hover:bg-stone-700"
              >
                Reset
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

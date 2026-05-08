import { AdapterStatus } from "../api/client";

type Props = {
  adapters: AdapterStatus[];
};

function statusTone(adapter: AdapterStatus): string {
  if (!adapter.connected || adapter.last_message_age_ms === null || adapter.last_message_age_ms > 30_000) {
    return "bg-rose-500";
  }
  if (adapter.last_message_age_ms > 5_000 || adapter.reconnect_count > 0 || adapter.gap_count > 0) {
    return "bg-amber-500";
  }
  return "bg-emerald-500";
}

function statusLabel(adapter: AdapterStatus): string {
  if (!adapter.connected) {
    return "Disconnected";
  }
  if (adapter.last_message_age_ms === null) {
    return "Waiting";
  }
  if (adapter.last_message_age_ms > 30_000) {
    return "Stale";
  }
  if (adapter.last_message_age_ms > 5_000 || adapter.reconnect_count > 0 || adapter.gap_count > 0) {
    return "Degraded";
  }
  return "Live";
}

export function AdapterStatusBanner({ adapters }: Props) {
  return (
    <section className="rounded-[2rem] border border-stone-300 bg-white/80 p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-stone-500">Adapter Health</p>
          <h2 className="mt-2 font-display text-2xl text-ink">Exchange Connectivity</h2>
        </div>
        <p className="text-sm text-stone-500">Polled every 2 seconds</p>
      </div>
      <div className="mt-5 grid gap-4 md:grid-cols-3">
        {adapters.length === 0 ? (
          <article className="rounded-3xl border border-dashed border-stone-300 bg-stone-50 p-4 text-sm text-stone-500 md:col-span-3">
            Adapter status is unavailable until the backend exposes `/api/adapters`.
          </article>
        ) : null}
        {adapters.map((adapter) => (
          <article key={adapter.exchange} className="rounded-3xl border border-stone-200 bg-stone-50 p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className={`h-3 w-3 rounded-full ${statusTone(adapter)}`} />
                <strong className="capitalize text-ink">{adapter.exchange}</strong>
              </div>
              <span className="text-sm text-stone-500">{statusLabel(adapter)}</span>
            </div>
            <div className="mt-3 space-y-1 text-sm text-stone-600">
              <p>
                Last message:{" "}
                {adapter.last_message_age_ms === null ? "--" : `${(adapter.last_message_age_ms / 1000).toFixed(1)}s ago`}
              </p>
              <p>Reconnects: {adapter.reconnect_count}</p>
              <p>Gap events: {adapter.gap_count}</p>
              <p className="truncate" title={adapter.last_error ?? ""}>
                Last error: {adapter.last_error ?? "--"}
              </p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

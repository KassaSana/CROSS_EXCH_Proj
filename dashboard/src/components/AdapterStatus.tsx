import { AdapterStatus, BookStatus } from "../api/client";
import { Async } from "../lib/async";
import { age, count } from "../lib/format";
import { Health, HealthMark } from "./HealthMark";
import { Panel, PanelTone } from "./Panel";
import { Placeholder } from "./Placeholder";

type Props = {
  adapters: Async<AdapterStatus[]>;
  books: Record<string, BookStatus>;
  feedLive: boolean;
  onRetry: () => void;
};

type Assessment = {
  health: Health;
  label: string;
};

function exchangeBooks(
  adapter: AdapterStatus,
  books: Record<string, BookStatus>,
): BookStatus[] {
  return Object.values(books).filter((book) => book.exchange === adapter.exchange);
}

function assess(adapter: AdapterStatus, books: BookStatus[]): Assessment {
  if (!adapter.connected) {
    return { health: "down", label: "Disconnected" };
  }
  if (adapter.last_message_age_ms === null) {
    return { health: "stale", label: "Waiting for first message" };
  }
  if (adapter.last_message_age_ms > 30_000) {
    return { health: "down", label: "Stale" };
  }
  if (books.length === 0 || books.every((book) => !book.eligible)) {
    return { health: "stale", label: "Rebuilding books" };
  }
  if (books.some((book) => !book.eligible)) {
    return { health: "degraded", label: "Partially eligible" };
  }
  if (
    adapter.last_message_age_ms > 5_000 ||
    adapter.reconnect_count > 0 ||
    adapter.gap_count > 0
  ) {
    return { health: "degraded", label: "Recovered from interruption" };
  }
  return { health: "ok", label: "Live" };
}

const RANK: Record<Health, number> = { ok: 0, degraded: 1, stale: 2, down: 3 };

function panelTone(worst: Health): PanelTone {
  if (worst === "down") {
    return "crit";
  }
  return worst === "ok" ? "default" : "warn";
}

export function AdapterStatusBanner({ adapters, books, feedLive, onRetry }: Props) {
  if (adapters.state === "failed") {
    return (
      <Placeholder
        state="failed"
        title="Cannot reach the adapter health endpoint"
        detail={adapters.error}
        onRetry={onRetry}
      />
    );
  }

  if (adapters.state === "loading") {
    return (
      <Panel title="Exchange connectivity">
        <p className="px-4 py-4 text-xs text-ink-3">Checking adapters.</p>
      </Panel>
    );
  }

  const rows = adapters.data.map((adapter) => {
    const statuses = exchangeBooks(adapter, books);
    return {
      adapter,
      statuses,
      assessment: assess(adapter, statuses),
      eligible: statuses.filter((book) => book.eligible).length,
    };
  });

  const worst = rows.reduce<Health>(
    (acc, row) => (RANK[row.assessment.health] > RANK[acc] ? row.assessment.health : acc),
    "ok",
  );
  const troubled = rows.filter((row) => row.assessment.health !== "ok").length;

  return (
    <Panel
      title="Exchange connectivity"
      meta={
        troubled === 0
          ? `${rows.length} venues nominal`
          : `${troubled} of ${rows.length} venues need attention`
      }
      tone={feedLive ? panelTone(worst) : "warn"}
    >
      {rows.length === 0 ? (
        <p className="px-4 py-4 text-xs text-ink-3">No adapters reported.</p>
      ) : (
        <ul className="divide-y divide-line-soft">
          {rows.map(({ adapter, statuses, assessment, eligible }) => (
            <li
              key={adapter.exchange}
              className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2.5"
            >
              <span className="flex min-w-[13rem] items-center gap-2.5">
                <HealthMark health={assessment.health} />
                <span className="text-xs font-medium capitalize text-ink">
                  {adapter.exchange}
                </span>
                <span
                  className={`text-micro ${
                    assessment.health === "ok" ? "text-ink-3" : "text-ink-2"
                  }`}
                >
                  {assessment.label}
                </span>
              </span>

              <dl className="flex flex-wrap items-center gap-x-5 gap-y-1 text-micro text-ink-3">
                <div className="flex gap-1.5">
                  <dt>Last message</dt>
                  <dd className="num text-ink-2">{age(adapter.last_message_age_ms)}</dd>
                </div>
                <div className="flex gap-1.5">
                  <dt>Books</dt>
                  <dd className="num text-ink-2">
                    {eligible}/{statuses.length}
                  </dd>
                </div>
                <div className="flex gap-1.5">
                  <dt>Reconnects</dt>
                  <dd
                    className={`num ${adapter.reconnect_count > 0 ? "text-warn" : "text-ink-2"}`}
                  >
                    {count(adapter.reconnect_count)}
                  </dd>
                </div>
                <div className="flex gap-1.5">
                  <dt>Gaps</dt>
                  <dd className={`num ${adapter.gap_count > 0 ? "text-warn" : "text-ink-2"}`}>
                    {count(adapter.gap_count)}
                  </dd>
                </div>
              </dl>

              {adapter.last_error !== null ? (
                <p
                  className="w-full truncate text-micro text-crit"
                  title={adapter.last_error}
                >
                  {adapter.last_error}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

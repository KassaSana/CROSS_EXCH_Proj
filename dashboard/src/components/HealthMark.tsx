/**
 * Health is encoded by shape first and colour second, so the state survives
 * colour-vision deficiency, greyscale printing and forced-colours mode.
 * "ok" is deliberately uncoloured: a healthy system should be quiet.
 */
export type Health = "ok" | "degraded" | "stale" | "down";

const TONE: Record<Health, string> = {
  ok: "text-ink-3",
  degraded: "text-warn",
  stale: "text-warn",
  down: "text-crit",
};

export function HealthMark({ health }: { health: Health }) {
  return (
    <svg
      viewBox="0 0 10 10"
      width="10"
      height="10"
      aria-hidden="true"
      focusable="false"
      className={`shrink-0 ${TONE[health]}`}
    >
      {health === "ok" ? <circle cx="5" cy="5" r="3" fill="currentColor" /> : null}
      {health === "degraded" ? (
        <path d="M5 0.8 9.6 9.2 0.4 9.2 Z" fill="currentColor" />
      ) : null}
      {health === "stale" ? (
        <circle cx="5" cy="5" r="3.4" fill="none" stroke="currentColor" strokeWidth="1.6" />
      ) : null}
      {health === "down" ? (
        <path
          d="M1.4 1.4 8.6 8.6 M8.6 1.4 1.4 8.6"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
      ) : null}
    </svg>
  );
}

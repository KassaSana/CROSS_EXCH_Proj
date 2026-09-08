import { ReactNode } from "react";

/**
 * The one container primitive. A hairline and a surface, nothing else.
 * Elevation is reserved for urgency, not decoration: a panel only gains a
 * coloured edge when something inside it needs attention.
 */
export type PanelTone = "default" | "warn" | "crit";

type Props = {
  title?: string;
  meta?: ReactNode;
  tone?: PanelTone;
  className?: string;
  children: ReactNode;
};

const TONE_BORDER: Record<PanelTone, string> = {
  default: "border-line",
  warn: "border-warn/45",
  crit: "border-crit/55",
};

export function Panel({ title, meta, tone = "default", className = "", children }: Props) {
  const hasHeader = title !== undefined || meta !== undefined;
  return (
    <section className={`rounded border bg-panel ${TONE_BORDER[tone]} ${className}`}>
      {hasHeader ? (
        <header className="flex items-baseline justify-between gap-4 border-b border-line-soft px-4 py-2.5">
          {title !== undefined ? (
            <h2 className="text-sm font-medium tracking-tight text-ink">{title}</h2>
          ) : (
            <span />
          )}
          {meta !== undefined ? <div className="text-micro text-ink-3">{meta}</div> : null}
        </header>
      ) : null}
      {children}
    </section>
  );
}

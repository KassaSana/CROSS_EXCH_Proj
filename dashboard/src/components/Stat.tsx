import { ReactNode } from "react";

type Props = {
  label: string;
  value: ReactNode;
  sub?: string;
};

/** One readout: a quiet label and a monospaced figure that will not shift as it ticks. */
export function Stat({ label, value, sub }: Props) {
  return (
    <div className="bg-panel px-4 py-3">
      <p className="text-micro text-ink-3">{label}</p>
      <p className="num mt-1.5 text-2xl font-medium text-ink">{value}</p>
      {sub !== undefined ? <p className="mt-1 text-micro text-ink-3">{sub}</p> : null}
    </div>
  );
}

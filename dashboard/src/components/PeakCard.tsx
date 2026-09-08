import { PeakMinute } from "../api/client";
import { count, dateTime, DASH, spreadPct } from "../lib/format";
import { Panel } from "./Panel";
import { Stat } from "./Stat";

type Props = {
  allTimeCount: number;
  allTimeMaxSpread: string;
  allTimePeakMinute: PeakMinute | null;
};

export function PeakCard({ allTimeCount, allTimeMaxSpread, allTimePeakMinute }: Props) {
  return (
    <Panel title="All-time peaks" meta="Across the full opportunity history" className="overflow-hidden">
      <div className="grid gap-px bg-line-soft sm:grid-cols-3">
        <Stat label="Total opportunities" value={count(allTimeCount)} />
        <Stat label="Widest spread observed" value={spreadPct(allTimeMaxSpread)} />
        <Stat
          label="Busiest minute"
          value={allTimePeakMinute === null ? DASH : count(allTimePeakMinute.count)}
          sub={
            allTimePeakMinute === null
              ? "Not enough history yet"
              : dateTime(allTimePeakMinute.minute_start_ns)
          }
        />
      </div>
    </Panel>
  );
}

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Timeseries, WindowKey } from "../api/client";
import { Async } from "../lib/async";
import { nsToMs } from "../lib/format";
import { Panel } from "./Panel";
import { Placeholder } from "./Placeholder";

type Props = {
  data: Async<Timeseries>;
  window: WindowKey;
  windowLabel: string;
  onRetry: () => void;
};

const GRID = "#1E2A36";
const AXIS_INK = "#7C8B9B";
const SIGNAL = "#3ECF8E";

function formatTick(ns: string, window: WindowKey): string {
  const date = new Date(nsToMs(ns));
  if (window === "1h" || window === "4h") {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

export function OpportunitiesChart({ data, window, windowLabel, onRetry }: Props) {
  if (data.state === "failed") {
    return (
      <Placeholder
        state="failed"
        title="Could not load the timeseries"
        detail={data.error}
        onRetry={onRetry}
      />
    );
  }

  if (data.state === "loading") {
    return (
      <Panel title="Opportunities over time">
        <p className="px-4 py-6 text-xs text-ink-3">Loading timeseries.</p>
      </Panel>
    );
  }

  const points = data.data.points;
  if (points.length === 0 || points.every((point) => point.count === 0)) {
    return (
      <Placeholder
        state="empty"
        title="No opportunities recorded in this window"
        detail="The chart draws itself once the detector logs its first spread."
      />
    );
  }

  // A single bucket is a number, not a trend. Plotting it produces one
  // floating dot in an empty grid, which reads as a broken chart.
  if (points.length < 2) {
    return (
      <Placeholder
        state="empty"
        title={`${points[0].count} opportunities so far, all inside one bucket`}
        detail="At least two buckets of history are needed before a trend means anything."
      />
    );
  }

  const chartData = points.map((point) => ({
    count: point.count,
    label: formatTick(point.bucket_start_ns, window),
  }));

  return (
    <Panel
      title={`Opportunities over the last ${windowLabel}`}
      meta={`${points.length} buckets · ${points.reduce(
        (total, point) => total + point.count,
        0,
      )} detections`}
    >
      <div className="h-64 px-2 pb-2 pt-4">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 4, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="opportunity-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={SIGNAL} stopOpacity={0.28} />
                <stop offset="100%" stopColor={SIGNAL} stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke={GRID} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: AXIS_INK, fontFamily: "IBM Plex Mono, monospace" }}
              axisLine={{ stroke: GRID }}
              tickLine={false}
              minTickGap={24}
            />
            <YAxis
              tick={{ fontSize: 11, fill: AXIS_INK, fontFamily: "IBM Plex Mono, monospace" }}
              axisLine={false}
              tickLine={false}
              allowDecimals={false}
              width={36}
            />
            <Tooltip
              cursor={{ stroke: "#3D4C5C", strokeWidth: 1 }}
              contentStyle={{
                backgroundColor: "#1C2733",
                border: "1px solid #263341",
                borderRadius: "3px",
                fontSize: 12,
                fontFamily: "IBM Plex Mono, monospace",
                color: "#E6ECF2",
              }}
              labelStyle={{ color: "#9BAAB9", fontFamily: "IBM Plex Sans, sans-serif" }}
              formatter={(value: number) => [value, "Opportunities"]}
            />
            <Area
              type="monotone"
              dataKey="count"
              stroke={SIGNAL}
              strokeWidth={2}
              fill="url(#opportunity-fill)"
              dot={false}
              activeDot={{ r: 4, fill: SIGNAL, stroke: "#0F151C", strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

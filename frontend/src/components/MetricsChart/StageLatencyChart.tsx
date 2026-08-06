import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { StageMetric } from "@/models";

export interface StageLatencyChartProps {
  stageMetrics: StageMetric[];
}

/** Average latency per pipeline stage, from `MetricsSnapshot.stage_metrics`. */
export function StageLatencyChart({ stageMetrics }: StageLatencyChartProps) {
  if (stageMetrics.length === 0) {
    return <p className="text-sm text-muted-foreground">No stage latency recorded yet.</p>;
  }

  const data = stageMetrics.map((metric) => ({
    stage: metric.stage.replaceAll("_", " "),
    averageMs: Number(metric.average_latency_ms.toFixed(2)),
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={data} layout="vertical" margin={{ left: 24 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" horizontal={false} />
        <XAxis type="number" tick={{ fontSize: 12 }} stroke="var(--color-muted-foreground)" />
        <YAxis
          dataKey="stage"
          type="category"
          width={110}
          tick={{ fontSize: 12 }}
          stroke="var(--color-muted-foreground)"
        />
        <Tooltip
          formatter={(value) => [`${value} ms`, "Average latency"]}
          contentStyle={{
            background: "var(--color-popover)",
            border: "1px solid var(--color-border)",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
        <Bar dataKey="averageMs" fill="var(--color-primary)" radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

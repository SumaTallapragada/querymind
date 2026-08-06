import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { MetricsSnapshot } from "@/models";

export interface PipelineOutcomeChartProps {
  metrics: Pick<MetricsSnapshot, "pipeline_success_count" | "pipeline_failure_count">;
}

const COLORS = ["var(--color-success)", "var(--color-destructive)"];
const DEFAULT_COLOR = "var(--color-muted-foreground)";

/** Successful vs. failed pipeline runs, from `MetricsSnapshot`. */
export function PipelineOutcomeChart({ metrics }: PipelineOutcomeChartProps) {
  const total = metrics.pipeline_success_count + metrics.pipeline_failure_count;
  if (total === 0) {
    return <p className="text-sm text-muted-foreground">No pipeline runs recorded yet.</p>;
  }

  const data = [
    { name: "Success", value: metrics.pipeline_success_count },
    { name: "Failure", value: metrics.pipeline_failure_count },
  ];

  return (
    <ResponsiveContainer width="100%" height={220}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={50} outerRadius={80} paddingAngle={2}>
          {data.map((entry, index) => (
            <Cell key={entry.name} fill={COLORS[index] ?? DEFAULT_COLOR} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            background: "var(--color-popover)",
            border: "1px solid var(--color-border)",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

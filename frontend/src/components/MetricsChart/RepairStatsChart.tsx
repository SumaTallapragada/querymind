import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { MetricsSnapshot } from "@/models";

export interface RepairStatsChartProps {
  metrics: Pick<MetricsSnapshot, "repair_attempted_count" | "repair_success_count">;
}

/** Repair attempts vs. successful repairs, from `MetricsSnapshot`. */
export function RepairStatsChart({ metrics }: RepairStatsChartProps) {
  if (metrics.repair_attempted_count === 0) {
    return <p className="text-sm text-muted-foreground">No repairs attempted yet.</p>;
  }

  const data = [
    { name: "Attempted", count: metrics.repair_attempted_count },
    { name: "Succeeded", count: metrics.repair_success_count },
  ];

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 12 }} stroke="var(--color-muted-foreground)" />
        <YAxis tick={{ fontSize: 12 }} stroke="var(--color-muted-foreground)" allowDecimals={false} />
        <Tooltip
          contentStyle={{
            background: "var(--color-popover)",
            border: "1px solid var(--color-border)",
            borderRadius: 8,
            fontSize: 12,
          }}
        />
        <Bar dataKey="count" fill="var(--color-warning)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

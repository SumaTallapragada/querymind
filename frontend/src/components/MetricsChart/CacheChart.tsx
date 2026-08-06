import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { MetricsSnapshot } from "@/models";

export interface CacheChartProps {
  metrics: Pick<MetricsSnapshot, "cache_hit_count" | "cache_miss_count">;
}

const COLORS = ["var(--color-success)", "var(--color-muted-foreground)"];
const DEFAULT_COLOR = "var(--color-border)";

/** Cache hit vs. miss counts, from `MetricsSnapshot`. */
export function CacheChart({ metrics }: CacheChartProps) {
  const total = metrics.cache_hit_count + metrics.cache_miss_count;
  if (total === 0) {
    return <p className="text-sm text-muted-foreground">No cache activity recorded yet.</p>;
  }

  const data = [
    { name: "Hits", value: metrics.cache_hit_count },
    { name: "Misses", value: metrics.cache_miss_count },
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

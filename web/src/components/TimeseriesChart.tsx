import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useTranslation } from "react-i18next";
import type { QueryRow } from "../lib/api";
import { formatBucket, formatNumber } from "../lib/format";
import { SkeletonRows } from "./widgets";

export default function TimeseriesChart({
  rows,
  compareRows,
  granularity,
  annotations,
}: {
  rows: QueryRow[] | undefined;
  compareRows?: QueryRow[] | null;
  granularity: string;
  annotations?: { bucket: string; label: string }[];
}) {
  const { t } = useTranslation();
  if (!rows) return <SkeletonRows />;

  const data = rows.map((row, index) => ({
    bucket: formatBucket(String(row.bucket), granularity),
    value: row.value ?? 0,
    previous: compareRows?.[index]?.value ?? null,
  }));

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -18 }}>
          <defs>
            <linearGradient id="flame-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-flame)" stopOpacity={0.25} />
              <stop offset="100%" stopColor="var(--color-flame)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--line)" strokeDasharray="2 4" vertical={false} />
          {annotations?.map((annotation, index) => (
            <ReferenceLine
              key={index}
              x={annotation.bucket}
              stroke="var(--ink-soft)"
              strokeDasharray="4 3"
              label={{
                value: "▾ " + annotation.label,
                position: "insideTopRight",
                fill: "var(--ink-soft)",
                fontSize: 10,
              }}
            />
          ))}
          <XAxis
            dataKey="bucket"
            tick={{ fill: "var(--ink-soft)", fontSize: 11 }}
            axisLine={{ stroke: "var(--line)" }}
            tickLine={false}
            minTickGap={28}
          />
          <YAxis
            tick={{ fill: "var(--ink-soft)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(value: number) => formatNumber(value)}
          />
          <Tooltip
            cursor={{ stroke: "var(--color-flame)", strokeOpacity: 0.3 }}
            contentStyle={{
              background: "var(--surface)",
              border: "1px solid var(--line)",
              borderRadius: 10,
              fontSize: 12,
              color: "var(--ink)",
            }}
            formatter={(value: number, name: string) => [
              formatNumber(value),
              name === "previous" ? t("period.vsPrevious") : t("web.timeseries"),
            ]}
          />
          {compareRows && (
            <Line
              dataKey="previous"
              stroke="var(--ink-soft)"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              dot={false}
              type="monotone"
            />
          )}
          <Area
            dataKey="value"
            stroke="var(--color-flame)"
            strokeWidth={2}
            fill="url(#flame-fill)"
            type="monotone"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

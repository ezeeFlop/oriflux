import i18n from "../i18n";

const locale = () => (i18n.language === "fr" ? "fr-FR" : "en-GB");

export function formatNumber(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat(locale(), {
    notation: value >= 10_000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatPercent(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${new Intl.NumberFormat(locale(), { maximumFractionDigits: 1 }).format(value)} %`;
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null || Number.isNaN(seconds)) return "—";
  const s = Math.round(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, "0")}s`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, "0")}m`;
}

export function formatMs(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`;
}

/** Signed delta between a value and its comparison, as a percentage. */
export function deltaPercent(current: number | null, previous: number | null): number | null {
  if (current === null || previous === null || previous === 0) return null;
  return ((current - previous) / previous) * 100;
}

export function formatBucket(bucket: string, granularity: string): string {
  const date = new Date(bucket);
  if (granularity === "hour") {
    return new Intl.DateTimeFormat(locale(), { hour: "2-digit", minute: "2-digit" }).format(date);
  }
  if (granularity === "month") {
    return new Intl.DateTimeFormat(locale(), { month: "short", year: "2-digit" }).format(date);
  }
  return new Intl.DateTimeFormat(locale(), { day: "2-digit", month: "short" }).format(date);
}

/** Format a value according to its registry metric (rates → %, latencies →
 *  ms, everything else → plain numbers). */
export function formatMetricValue(metric: string, value: number | null): string {
  if (metric.includes("rate")) return formatPercent(value);
  if (metric.includes("latency") || metric.startsWith("web_vital")) return formatMs(value);
  if (metric === "session_duration") return formatDuration(value);
  return formatNumber(value);
}

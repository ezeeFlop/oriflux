import type { Period } from "./api";

export type PeriodKey = "24h" | "7d" | "30d" | "90d" | "12m";

export const PERIOD_KEYS: PeriodKey[] = ["24h", "7d", "30d", "90d", "12m"];

const HOURS: Record<PeriodKey, number> = {
  "24h": 24,
  "7d": 24 * 7,
  "30d": 24 * 30,
  "90d": 24 * 90,
  "12m": 24 * 365,
};

/** Granularity matched to the window so charts stay readable (and the
 *  registry's hour-granularity cap is respected). */
export function granularityFor(key: PeriodKey): "hour" | "day" | "week" | "month" {
  if (key === "24h") return "hour";
  if (key === "7d" || key === "30d") return "day";
  if (key === "90d") return "week";
  return "month";
}

export function periodFor(key: PeriodKey, now = new Date()): Period {
  const end = now.toISOString();
  const start = new Date(now.getTime() - HOURS[key] * 3600 * 1000).toISOString();
  return { start, end };
}

export function lastMinutes(minutes: number, now = new Date()): Period {
  return {
    start: new Date(now.getTime() - minutes * 60 * 1000).toISOString(),
    end: now.toISOString(),
  };
}

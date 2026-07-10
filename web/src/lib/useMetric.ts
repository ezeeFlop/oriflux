/** The one data hook: every widget declares a registry query, React Query
 *  caches it. There is no other way to fetch numbers in this app. */

import { useQuery } from "@tanstack/react-query";
import { runQuery, type QueryFilter, type QueryResponse } from "./api";
import { useDashboard } from "./state";

interface MetricOptions {
  metric: string;
  dimensions?: string[];
  extraFilters?: QueryFilter[];
  withGranularity?: boolean;
  projectId: string;
  /** override the shared filters (e.g. API view has no traffic_class) */
  projectOnly?: boolean;
  refetchIntervalMs?: number;
  periodOverride?: { start: string; end: string };
  granularityOverride?: "hour" | "day" | "week" | "month";
}

export function useMetric(options: MetricOptions) {
  const { period, granularity, compare, webFilters } = useDashboard();
  const filters: QueryFilter[] = options.projectOnly
    ? [{ dimension: "project_id", op: "eq", value: options.projectId }]
    : webFilters(options.projectId);
  if (options.extraFilters) filters.push(...options.extraFilters);

  const request = {
    metric: options.metric,
    dimensions: options.dimensions ?? [],
    filters,
    granularity: options.withGranularity
      ? (options.granularityOverride ?? granularity)
      : null,
    period: options.periodOverride ?? period,
    compare_to: compare && !options.periodOverride ? ("previous_period" as const) : null,
  };

  return useQuery<QueryResponse>({
    queryKey: ["query", request],
    queryFn: () => runQuery(request),
    refetchInterval: options.refetchIntervalMs,
    placeholderData: (previous) => previous,
  });
}

export function scalar(response: QueryResponse | undefined): number | null {
  const value = response?.results?.[0]?.value;
  return value === undefined ? null : value;
}

export function compareScalar(response: QueryResponse | undefined): number | null {
  const value = response?.compare_results?.[0]?.value;
  return value === undefined || value === null ? null : value;
}

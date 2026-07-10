import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { PeriodPicker } from "../components/Shell";
import { Panel, RankedTable, SkeletonRows, StatCard } from "../components/widgets";
import type { QueryRow } from "../lib/api";
import { deltaPercent, formatMs, formatNumber, formatPercent } from "../lib/format";
import { compareScalar, scalar, useMetric } from "../lib/useMetric";

type SortKey = "volume" | "errors" | "p95";

function classColor(statusClass: string): string {
  if (statusClass === "5xx") return "text-down";
  if (statusClass === "4xx") return "text-flame";
  return "text-up";
}

function EndpointTable({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const [sortKey, setSortKey] = useState<SortKey>("volume");

  const volume = useMetric({
    metric: "api_requests", dimensions: ["endpoint"], projectId, projectOnly: true,
  });
  const errors = useMetric({
    metric: "api_error_rate_5xx", dimensions: ["endpoint"], projectId, projectOnly: true,
  });
  const p95 = useMetric({
    metric: "api_latency_p95", dimensions: ["endpoint"], projectId, projectOnly: true,
  });

  const merged = useMemo(() => {
    if (!volume.data) return undefined;
    const index = new Map<string, { volume: number; errors: number | null; p95: number | null }>();
    for (const row of volume.data.results) {
      index.set(String(row.endpoint), { volume: row.value ?? 0, errors: null, p95: null });
    }
    for (const row of errors.data?.results ?? []) {
      const entry = index.get(String(row.endpoint));
      if (entry) entry.errors = row.value;
    }
    for (const row of p95.data?.results ?? []) {
      const entry = index.get(String(row.endpoint));
      if (entry) entry.p95 = row.value;
    }
    const compare = new Map<string, number>(
      (volume.data.compare_results ?? []).map((row) => [String(row.endpoint), row.value ?? 0]),
    );
    return [...index.entries()]
      .map(([endpoint, values]) => ({
        endpoint,
        ...values,
        delta: deltaPercent(values.volume, compare.get(endpoint) ?? null),
      }))
      .sort((a, b) => {
        if (sortKey === "volume") return b.volume - a.volume;
        if (sortKey === "errors") return (b.errors ?? -1) - (a.errors ?? -1);
        return (b.p95 ?? -1) - (a.p95 ?? -1);
      })
      .slice(0, 15);
  }, [volume.data, errors.data, p95.data, sortKey]);

  const header = (key: SortKey, label: string) => (
    <button
      onClick={() => setSortKey(key)}
      className={`text-right text-xs font-semibold uppercase tracking-wide ${
        sortKey === key ? "text-flame" : "text-ink-soft hover:text-ink"
      }`}
    >
      {label} {sortKey === key ? "↓" : ""}
    </button>
  );

  return (
    <Panel title={t("api.endpoints")}>
      {!merged ? (
        <SkeletonRows />
      ) : merged.length === 0 ? (
        <p className="py-6 text-center text-sm text-ink-soft">{t("web.empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] border-collapse">
            <thead>
              <tr className="border-b border-line">
                <th className="pb-2 text-left text-xs font-semibold uppercase tracking-wide text-ink-soft">
                  {t("api.endpoint")}
                </th>
                <th className="pb-2 text-right">{header("volume", t("api.volume"))}</th>
                <th className="pb-2 text-right">{header("errors", t("api.errorRate"))}</th>
                <th className="pb-2 text-right">{header("p95", t("api.p95"))}</th>
              </tr>
            </thead>
            <tbody>
              {merged.map((row) => (
                <tr key={row.endpoint} className="border-b border-line/60 last:border-0">
                  <td className="max-w-[280px] truncate py-1.5 pr-3 font-mono text-xs">
                    {row.endpoint}
                  </td>
                  <td className="tnum py-1.5 text-right text-sm font-semibold">
                    {formatNumber(row.volume)}
                    {row.delta !== null && (
                      <span
                        className={`ml-1.5 text-xs ${row.delta > 0 ? "text-up" : "text-down"}`}
                      >
                        {row.delta > 0 ? "▲" : "▼"}
                        {Math.abs(row.delta).toFixed(0)}%
                      </span>
                    )}
                  </td>
                  <td
                    className={`tnum py-1.5 text-right text-sm ${
                      (row.errors ?? 0) > 2 ? "font-semibold text-down" : ""
                    }`}
                  >
                    {formatPercent(row.errors)}
                  </td>
                  <td className="tnum py-1.5 text-right text-sm">{formatMs(row.p95)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function ConsumerPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const volume = useMetric({
    metric: "api_requests", dimensions: ["consumer"], projectId, projectOnly: true,
  });
  const errors = useMetric({
    metric: "api_error_rate_5xx", dimensions: ["consumer"], projectId, projectOnly: true,
  });
  const errorByConsumer = new Map<string, number | null>(
    (errors.data?.results ?? []).map((row) => [String(row.consumer), row.value]),
  );
  return (
    <Panel title={t("api.consumers")}>
      <RankedTable
        rows={volume.data?.results}
        dimension="consumer"
        labelFor={(raw) => raw || t("api.anonymous")}
        valueFormatter={(value) => formatNumber(value)}
      />
      {volume.data && volume.data.results.length > 0 && (
        <p className="mt-2 text-xs text-ink-soft">
          {[...errorByConsumer.entries()]
            .filter(([, rate]) => (rate ?? 0) > 0)
            .slice(0, 3)
            .map(([consumer, rate]) => `${consumer || t("api.anonymous")}: ${formatPercent(rate)} 5xx`)
            .join(" · ")}
        </p>
      )}
    </Panel>
  );
}

export default function ApiView() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams();

  const requests = useMetric({ metric: "api_requests", projectId, projectOnly: true });
  const err4 = useMetric({ metric: "api_error_rate_4xx", projectId, projectOnly: true });
  const err5 = useMetric({ metric: "api_error_rate_5xx", projectId, projectOnly: true });
  const p95 = useMetric({ metric: "api_latency_p95", projectId, projectOnly: true });
  const statusClasses = useMetric({
    metric: "api_requests", dimensions: ["status_class"], projectId, projectOnly: true,
  });
  const callerGeo = useMetric({
    metric: "api_requests", dimensions: ["country"], projectId, projectOnly: true,
  });

  const stat = (
    query: ReturnType<typeof useMetric>,
    label: string,
    format: (value: number | null) => string,
    inverse = true,
  ) => (
    <StatCard
      label={label}
      value={format(scalar(query.data))}
      compareValue={
        query.data?.compare_results
          ? { current: scalar(query.data), previous: compareScalar(query.data) }
          : undefined
      }
      inverse={inverse}
    />
  );

  const statusRows: QueryRow[] | undefined = statusClasses.data?.results;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-xl font-bold tracking-tight">{t("api.title")}</h1>
        <PeriodPicker />
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stat(requests, t("metric.api_requests"), formatNumber, false)}
        {stat(err4, t("metric.api_error_rate_4xx"), formatPercent)}
        {stat(err5, t("metric.api_error_rate_5xx"), formatPercent)}
        {stat(p95, t("metric.api_latency_p95"), formatMs)}
      </div>

      <EndpointTable projectId={projectId} />

      <div className="grid gap-4 md:grid-cols-3">
        <Panel title={t("api.statusClasses")}>
          {!statusRows ? (
            <SkeletonRows />
          ) : (
            <ul className="space-y-2">
              {[...statusRows]
                .sort((a, b) => String(a.status_class).localeCompare(String(b.status_class)))
                .map((row) => {
                  const total = statusRows.reduce((sum, r) => sum + (r.value ?? 0), 0) || 1;
                  const share = ((row.value ?? 0) / total) * 100;
                  return (
                    <li key={String(row.status_class)} className="text-sm">
                      <div className="flex items-baseline justify-between">
                        <span className={`font-mono text-xs ${classColor(String(row.status_class))}`}>
                          {String(row.status_class)}
                        </span>
                        <span className="tnum font-semibold">{formatNumber(row.value)}</span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-line">
                        <div
                          className="h-1.5 rounded-full bg-flame"
                          style={{ width: `${Math.max(2, share)}%` }}
                        />
                      </div>
                    </li>
                  );
                })}
            </ul>
          )}
        </Panel>
        <ConsumerPanel projectId={projectId} />
        <Panel title={t("api.callerGeo")}>
          <RankedTable
            rows={callerGeo.data?.results}
            dimension="country"
            labelFor={(raw) => raw || t("api.unresolved")}
          />
        </Panel>
      </div>
    </div>
  );
}

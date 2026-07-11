import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import Choropleth from "../components/Choropleth";
import { Panel, RankedTable, SkeletonRows, StatCard, Tabs } from "../components/widgets";
import type { QueryRow } from "../lib/api";
import { deltaPercent, formatMs, formatNumber, formatPercent } from "../lib/format";
import { fetchInfra } from "../lib/api";
import { compareScalar, scalar, useMetric } from "../lib/useMetric";
import { useDashboard } from "../lib/state";

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

function InfraPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const infra = useQuery({
    queryKey: ["infra", projectId],
    queryFn: () => fetchInfra(projectId),
    refetchInterval: 30_000,
  });
  if (!infra.data?.available) return null;
  return (
    <Panel title={t("infra.title")}>
      <div className="grid grid-cols-3 gap-3 text-center">
        <div>
          <div className="tnum font-display text-2xl font-bold">
            {infra.data.cpu_percent?.toFixed(1)}%
          </div>
          <div className="text-xs text-ink-soft">CPU</div>
        </div>
        <div>
          <div className="tnum font-display text-2xl font-bold">
            {Math.round(infra.data.memory_mb ?? 0)} MB
          </div>
          <div className="text-xs text-ink-soft">RAM</div>
        </div>
        <div>
          <div className="tnum font-display text-2xl font-bold">{infra.data.containers}</div>
          <div className="text-xs text-ink-soft">{t("infra.containers")}</div>
        </div>
      </div>
      <p className="mt-2 text-[11px] text-ink-soft">
        {t("infra.note", { service: infra.data.service })}
      </p>
    </Panel>
  );
}

const GEO_METRICS = ["api_requests", "api_error_rate_5xx", "api_latency_p95"] as const;
type GeoMetric = (typeof GEO_METRICS)[number];

const GEO_FORMATTERS: Record<GeoMetric, (value: number | null) => string> = {
  api_requests: formatNumber,
  api_error_rate_5xx: formatPercent,
  api_latency_p95: formatMs,
};

/** Caller geography (issue #51): the same embedded choropleth as the web
 *  view, colored by volume, 5xx rate or p95 latency per caller country —
 *  where no web-analytics tool goes. Clicking a country cross-filters the
 *  whole API view (country only: the api aggregate has no region/city,
 *  by design of the 2000-key ingest cap). */
function ApiGeoPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const { geo, setGeo } = useDashboard();
  const [metric, setMetric] = useState<GeoMetric>("api_requests");

  const mapQuery = useMetric({
    metric, dimensions: ["country"], projectId, projectOnly: true, ignoreGeo: true,
  });
  const rows = mapQuery.data?.results ?? [];
  const values = new Map<string, number>(
    rows
      .filter((row) => typeof row.country === "string" && row.country !== "")
      .map((row) => [String(row.country), row.value ?? 0]),
  );
  const format = GEO_FORMATTERS[metric];

  return (
    <Panel
      title={t("api.callerGeo")}
      className="md:col-span-3"
      actions={
        <Tabs
          value={metric}
          options={GEO_METRICS}
          onChange={setMetric}
          labelFor={(option) => t(`metric.${option}`)}
        />
      }
    >
      <div className="grid gap-4 md:grid-cols-[2fr_1fr]">
        <Choropleth
          values={values}
          selected={geo.country}
          onSelect={(a2) => setGeo(a2 === geo.country ? null : a2, null)}
          formatValue={(value) => format(value)}
          legendLabel={t(`metric.${metric}`)}
        />
        <RankedTable
          rows={rows}
          dimension="country"
          labelFor={(raw) => raw || t("api.unresolved")}
          valueFormatter={(value) => format(value)}
          onRowClick={(raw) => raw && setGeo(raw === geo.country ? null : raw, null)}
        />
      </div>
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
      <h1 className="font-display text-xl font-bold tracking-tight">{t("api.title")}</h1>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {stat(requests, t("metric.api_requests"), formatNumber, false)}
        {stat(err4, t("metric.api_error_rate_4xx"), formatPercent)}
        {stat(err5, t("metric.api_error_rate_5xx"), formatPercent)}
        {stat(p95, t("metric.api_latency_p95"), formatMs)}
      </div>

      <EndpointTable projectId={projectId} />

      <InfraPanel projectId={projectId} />

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
        <ApiGeoPanel projectId={projectId} />
      </div>
    </div>
  );
}

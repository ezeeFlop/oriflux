/** Portfolio home (issues #10/#47) — one tile per product, anomalous first,
 *  plus recent alerts, insights, explained anomalies and the live globe
 *  (WebSocket with a 10 s polling fallback). */

import { useQueries, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation } from "react-router-dom";
import { Panel, RankedTable, ScreenSubtitle, SkeletonRows } from "../components/widgets";
import { listAlertEvents, listAnomalies, listInsights, runQuery, auth, type Project, type QueryResponse } from "../lib/api";
import { formatNumber, formatPercent } from "../lib/format";
import { lastMinutes, periodFor } from "../lib/periods";
import { useLive } from "../lib/useLive";
import AlertEventRow from "../components/AlertEventRow";
import WorldLive from "../components/WorldLive";
import { useDashboard } from "../lib/state";

const LIVE_POLL_MS = 10_000;
const TREND_POLL_MS = 60_000;

interface TileData {
  live: number | null;  // null = the query errored (never rendered as a 0)
  trend: { value: number }[];
  errorRate: number | null;
  anomaly: number;
}

function Sparkline({ points }: { points: { value: number }[] }) {
  if (points.length < 2) return <div className="h-8" />;
  const max = Math.max(...points.map((p) => p.value), 1);
  const step = 100 / (points.length - 1);
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(30 - (p.value / max) * 28).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 32" className="h-8 w-full" preserveAspectRatio="none" aria-hidden>
      <path d={path} fill="none" stroke="var(--color-flame)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function useTiles(projects: Project[]) {
  const projectFilter = (id: string) => [{ dimension: "project_id", op: "eq" as const, value: id }];

  const live = useQueries({
    queries: projects.map((project) => ({
      queryKey: ["live", project.id],
      queryFn: () =>
        runQuery({
          metric: "visitors",
          filters: projectFilter(project.id),
          period: lastMinutes(0.5),
        }),
      refetchInterval: LIVE_POLL_MS,
    })),
  });
  const trends = useQueries({
    queries: projects.map((project) => ({
      queryKey: ["trend", project.id],
      queryFn: () =>
        runQuery({
          metric: "pageviews",
          filters: projectFilter(project.id),
          granularity: "day",
          period: periodFor("7d"),
        }),
      refetchInterval: TREND_POLL_MS,
    })),
  });
  const errors = useQueries({
    queries: projects.map((project) => ({
      queryKey: ["err", project.id],
      queryFn: () =>
        runQuery({
          metric: "api_error_rate_5xx",
          filters: projectFilter(project.id),
          period: periodFor("24h"),
        }),
      refetchInterval: TREND_POLL_MS,
    })),
  });

  return useMemo(() => {
    const tiles = new Map<string, TileData>();
    projects.forEach((project, index) => {
      const liveValue = live[index]?.isError
        ? null
        : (live[index]?.data?.results?.[0]?.value ?? 0);
      const trendRows = (trends[index]?.data as QueryResponse | undefined)?.results ?? [];
      const trend = trendRows.map((row) => ({ value: row.value ?? 0 }));
      const errorRate = errors[index]?.data?.results?.[0]?.value ?? null;

      // anomaly heuristic (V1, deliberately simple): |today vs 7-day mean|
      // ratio + 5xx pressure — anomalous products float to the top
      const values = trend.map((p) => p.value);
      const mean = values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0;
      const today = values.at(-1) ?? 0;
      const trafficAnomaly = mean > 0 ? Math.abs(today - mean) / mean : 0;
      const anomaly = trafficAnomaly + (errorRate ?? 0) / 2;

      tiles.set(project.id, { live: liveValue, trend, errorRate, anomaly });
    });
    return tiles;
  }, [projects, live, trends, errors]);
}

function RevenueStrip() {
  const { t } = useTranslation();
  const revenue = useQuery({
    queryKey: ["portfolio-revenue"],
    queryFn: () =>
      runQuery({
        metric: "revenue",
        period: periodFor("30d"),
      }),
    refetchInterval: TREND_POLL_MS,
  });
  const value = revenue.data?.results?.[0]?.value;
  if (value === undefined || value === null || value === 0) return null;
  return (
    <div className="rounded-lg border border-line bg-surface px-3 py-1.5 text-sm">
      <span className="text-ink-soft">{t("revenue.mrrMovement")} </span>
      <strong className={`tnum ${value >= 0 ? "text-emerald-600" : "text-flame"}`}>
        {value >= 0 ? "+" : ""}
        {value.toFixed(0)} €
      </strong>
      <span className="ml-1 text-xs text-ink-soft">/ 30j</span>
    </div>
  );
}

function InsightsSection() {
  const { t } = useTranslation();
  const insights = useQuery({
    queryKey: ["insights", auth.orgId],
    queryFn: () => listInsights(auth.orgId ?? ""),
    enabled: Boolean(auth.orgId),
    refetchInterval: 300_000,
  });
  if (!insights.data || insights.data.length === 0) return null;
  return (
    <section>
      <h2 className="font-display text-base font-bold">{t("insights.title")}</h2>
      <div className="mt-2 space-y-1.5">
        {insights.data.slice(0, 6).map((insight) => (
          <div
            key={insight.id}
            className="flex flex-wrap items-baseline gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
          >
            <span className={insight.numbers.delta_pct >= 0 ? "text-emerald-600" : "text-flame"}>
              {insight.numbers.delta_pct >= 0 ? "▲" : "▼"}
            </span>
            <strong>{insight.project_name}</strong>
            <span className="flex-1">
              {insight.text ||
                `${t(`metric.${insight.metric}`)} : ${insight.numbers.current} (${
                  insight.numbers.delta_pct >= 0 ? "+" : ""
                }${insight.numbers.delta_pct}%)`}
            </span>
            <span className="tnum text-xs text-ink-soft">{insight.day}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

/** Recent alert events (#47): rule, metric, value, state — one click lands
 *  on the project's alerts screen. The diagnosis itself rides the alert
 *  notification (design of #36); the anomalies feed below carries its own. */
function AlertsSection() {
  const { t } = useTranslation();
  const { search } = useLocation();
  const events = useQuery({
    queryKey: ["alert-events", auth.orgId],
    queryFn: () => listAlertEvents(auth.orgId ?? ""),
    enabled: Boolean(auth.orgId),
    refetchInterval: 60_000,
  });
  if (!events.data || events.data.length === 0) return null;
  return (
    <section>
      <h2 className="font-display text-base font-bold">{t("home.recentAlerts")}</h2>
      <div className="mt-2 space-y-1.5">
        {events.data.slice(0, 5).map((event) => {
          const body = <AlertEventRow event={event} />;
          const rowClass =
            "flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm";
          return event.project_id ? (
            <Link
              key={event.id}
              to={{ pathname: `/p/${event.project_id}/alerts`, search }}
              className={`${rowClass} hover:border-flame`}
            >
              {body}
            </Link>
          ) : (
            <div key={event.id} className={rowClass}>
              {body}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function AnomaliesSection() {
  const { t } = useTranslation();
  const anomalies = useQuery({
    queryKey: ["anomalies", auth.orgId],
    queryFn: () => listAnomalies(auth.orgId ?? ""),
    enabled: Boolean(auth.orgId),
    refetchInterval: 60_000,
  });
  if (!anomalies.data || anomalies.data.length === 0) return null;
  return (
    <section>
      <h2 className="font-display text-base font-bold">{t("anomalies.title")}</h2>
      <div className="mt-2 space-y-1.5">
        {anomalies.data.slice(0, 6).map((anomaly) => (
          <div
            key={anomaly.id}
            className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
          >
            <span className={anomaly.direction === "drop" ? "text-flame" : "text-amber-600"}>
              {anomaly.direction === "drop" ? "▼" : "▲"}
            </span>
            <strong>{anomaly.project_name}</strong>
            <span className="text-ink-soft">{t(`metric.${anomaly.metric}`)}</span>
            <span className="tnum font-semibold">
              {anomaly.deviation_pct > 0 ? "+" : ""}
              {anomaly.deviation_pct}%
            </span>
            <span className="text-xs text-ink-soft">
              {t("anomalies.vsExpected", { expected: anomaly.expected })} ·{" "}
              {new Date(anomaly.window_start).toLocaleString()}
            </span>
            {anomaly.explanation && (
              <p className="w-full text-xs text-ink-soft">{anomaly.explanation}</p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function LiveSection() {
  const { t } = useTranslation();
  const pagesNow = useQueries({
    queries: [
      {
        queryKey: ["live-pages"],
        queryFn: () =>
          runQuery({
            metric: "visitors",
            dimensions: ["page"],
            period: lastMinutes(30),
          }),
        refetchInterval: LIVE_POLL_MS,
      },
      {
        queryKey: ["live-countries"],
        queryFn: () =>
          runQuery({
            metric: "visitors",
            dimensions: ["country"],
            period: lastMinutes(30),
          }),
        refetchInterval: LIVE_POLL_MS,
      },
    ],
  });

  const live = useLive();
  const pageRows = live ? live.pages : pagesNow[0]?.data?.results;
  const countryRows = live ? live.countries : pagesNow[1]?.data?.results;
  return (
    <div className="space-y-4">
      <Panel
        title={t("home.liveGlobe")}
        actions={
          live ? (
            <span className="text-[10px] uppercase text-emerald-600">ws</span>
          ) : undefined
        }
      >
        <WorldLive countries={(countryRows ?? []).map((row) => ({
          country: String((row as { country?: unknown }).country ?? ""),
          value: Number((row as { value?: unknown }).value ?? 0),
        }))} />
      </Panel>
      <div className="grid gap-4 md:grid-cols-2">
        <Panel title={t("home.topPagesNow")}>
          <RankedTable rows={pageRows} dimension="page" />
        </Panel>
        <Panel title={t("home.topCountriesNow")}>
          <RankedTable rows={countryRows} dimension="country" />
        </Panel>
      </div>
    </div>
  );
}

export default function HomeView() {
  const { t } = useTranslation();
  const { search } = useLocation();
  const { projects } = useDashboard();
  const tiles = useTiles(projects);

  const sorted = [...projects].sort(
    (a, b) => (tiles.get(b.id)?.anomaly ?? 0) - (tiles.get(a.id)?.anomaly ?? 0),
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="font-display text-xl font-bold tracking-tight">{t("home.title")}</h1>
        <span className="flex items-center gap-1.5 text-xs text-ink-soft">
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-flame" aria-hidden />
          {t("home.updated")}
        </span>
      </div>
      <ScreenSubtitle id="home" />

      {projects.length === 0 ? (
        <Panel title={t("home.title")}>
          <p className="py-6 text-center text-sm text-ink-soft">{t("home.noProjects")}</p>
        </Panel>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((project) => {
            const tile = tiles.get(project.id);
            return (
              <Link
                key={project.id}
                to={{ pathname: `/p/${project.id}/overview`, search }}
                className="rise group rounded-xl border border-line bg-surface p-4 transition-shadow hover:shadow-[0_4px_20px_rgba(30,20,10,0.08)]"
              >
                <div className="flex items-baseline justify-between">
                  <h2 className="font-display text-base font-bold group-hover:text-flame">
                    {project.name}
                  </h2>
                  {(tile?.errorRate ?? 0) > 2 && (
                    <span className="rounded-full bg-down/10 px-2 py-0.5 text-[11px] font-semibold text-down">
                      {formatPercent(tile?.errorRate ?? null)} 5xx
                    </span>
                  )}
                </div>
                {tile ? (
                  <>
                    <div className="mt-2 flex items-baseline gap-2">
                      <span
                        className="tnum font-display text-3xl font-bold"
                        title={tile.live === null ? "query failed" : undefined}
                      >
                        {tile.live === null ? "–" : formatNumber(tile.live)}
                      </span>
                      <span className="text-xs text-ink-soft">{t("home.liveVisitors")}</span>
                    </div>
                    <div className="mt-3">
                      <Sparkline points={tile.trend} />
                      <div className="mt-1 flex justify-between text-[11px] text-ink-soft">
                        <span>{t("home.trend7d")}</span>
                        <span className="tnum">
                          {formatPercent(tile.errorRate)} · {t("home.apiErrors")}
                        </span>
                      </div>
                    </div>
                  </>
                ) : (
                  <SkeletonRows />
                )}
              </Link>
            );
          })}
        </div>
      )}

      <h2 className="font-display text-base font-bold">{t("home.liveNow")}</h2>
      <RevenueStrip />
      <AlertsSection />
      <InsightsSection />
      <AnomaliesSection />
      <LiveSection />
    </div>
  );
}

/** Project overview (issue #68) — the /p/:id cockpit answering "is this
 *  product doing fine, and what changed?" in five seconds: a KPI band
 *  (web + API + live) always compared to the previous period, the combined
 *  web+API trend, the project's recent alerts/annotations, and shortcuts.
 *  Every number flows through the typed registry, like everywhere else. */

import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useParams } from "react-router-dom";

import AlertEventRow from "../components/AlertEventRow";
import TimeseriesChart from "../components/TimeseriesChart";
import { Panel, ScreenSubtitle, StatCard } from "../components/widgets";
import { auth, listAlertEvents, listAnnotations, runQuery } from "../lib/api";
import { formatMs, formatNumber, formatPercent } from "../lib/format";
import { lastMinutes } from "../lib/periods";
import { useDashboard } from "../lib/state";
import { compareScalar, scalar, useMetric } from "../lib/useMetric";

const LIVE_POLL_MS = 10_000;

const SHORTCUTS = [
  { key: "web", path: "web" },
  { key: "api", path: "api" },
  { key: "live", path: "live" },
  { key: "alerts", path: "alerts" },
] as const;

function kpiCard(
  query: ReturnType<typeof useMetric>,
  term: string,
  format: (value: number | null) => string,
  inverse = false,
) {
  return (
    <StatCard
      term={term}
      value={format(scalar(query.data))}
      compareValue={
        query.data?.compare_results
          ? { current: scalar(query.data), previous: compareScalar(query.data) }
          : undefined
      }
      inverse={inverse}
    />
  );
}

/** The bridge to the pedagogy slice (#70): a project that emitted nothing
 *  shows its instrumentation state instead of mute zeros. */
function InstrumentationNotice({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const { search } = useLocation();
  return (
    <div className="rounded-xl border border-flame/40 bg-flame-soft/40 px-4 py-3 text-sm">
      <p className="font-semibold">{t("overview.notInstrumented")}</p>
      <p className="mt-1 text-ink-soft">{t("overview.instrumentHint")}</p>
      <Link
        to={{ pathname: `/p/${projectId}/settings`, search }}
        className="mt-2 inline-block rounded-md bg-flame px-3 py-1.5 text-sm font-semibold text-white hover:bg-flame-strong"
      >
        {t("overview.openSettings")}
      </Link>
    </div>
  );
}

export default function OverviewView() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams();
  const { search } = useLocation();
  const { period, granularity, projects } = useDashboard();
  const projectName = projects.find((p) => p.id === projectId)?.name ?? "";

  const visitors = useMetric({ metric: "visitors", projectId, projectOnly: true, forceCompare: true });
  const pageviews = useMetric({ metric: "pageviews", projectId, projectOnly: true, forceCompare: true });
  const sessions = useMetric({ metric: "sessions", projectId, projectOnly: true, forceCompare: true });
  const apiRequests = useMetric({ metric: "api_requests", projectId, projectOnly: true, forceCompare: true });
  const apiErrors = useMetric({ metric: "api_error_rate_5xx", projectId, projectOnly: true, forceCompare: true });
  const apiP95 = useMetric({ metric: "api_latency_p95", projectId, projectOnly: true, forceCompare: true });

  const liveNow = useQuery({
    queryKey: ["overview-live", projectId],
    queryFn: () =>
      runQuery({
        metric: "visitors",
        filters: [{ dimension: "project_id", op: "eq", value: projectId }],
        period: lastMinutes(0.5),
      }),
    refetchInterval: LIVE_POLL_MS,
  });

  const webTrend = useMetric({
    metric: "pageviews", withGranularity: true, projectId, projectOnly: true,
  });
  const apiTrend = useMetric({
    metric: "api_requests", withGranularity: true, projectId, projectOnly: true,
  });

  const alertEvents = useQuery({
    queryKey: ["alert-events", auth.orgId],
    queryFn: () => listAlertEvents(auth.orgId ?? ""),
    enabled: Boolean(auth.orgId),
    refetchInterval: 60_000,
  });
  const projectAlerts = (alertEvents.data ?? [])
    .filter((event) => event.project_id === projectId)
    .slice(0, 5);

  const annotations = useQuery({
    queryKey: ["annotations", projectId, period],
    queryFn: () => listAnnotations(projectId, period),
  });
  const recentAnnotations = [...(annotations.data ?? [])]
    .sort((a, b) => b.happened_at.localeCompare(a.happened_at))
    .slice(0, 5);

  // "emitted nothing" = both domains resolved to zero over the period —
  // null values (failed query) must not masquerade as "not instrumented"
  const notInstrumented =
    visitors.data !== undefined &&
    pageviews.data !== undefined &&
    apiRequests.data !== undefined &&
    (scalar(visitors.data) ?? 0) === 0 &&
    (scalar(pageviews.data) ?? 0) === 0 &&
    (scalar(apiRequests.data) ?? 0) === 0;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="font-display text-xl font-bold tracking-tight">
          {t("nav.overview")}
          {projectName ? ` — ${projectName}` : ""}
        </h1>
      </div>
      <ScreenSubtitle id="overview" />

      {notInstrumented && <InstrumentationNotice projectId={projectId} />}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-7">
        {kpiCard(visitors, "visitors", formatNumber)}
        {kpiCard(pageviews, "pageviews", formatNumber)}
        {kpiCard(sessions, "sessions", formatNumber)}
        {kpiCard(apiRequests, "api_requests", formatNumber)}
        {kpiCard(apiErrors, "api_error_rate_5xx", formatPercent, true)}
        {kpiCard(apiP95, "api_latency_p95", formatMs, true)}
        <StatCard
          label={t("overview.liveNow")}
          value={formatNumber(liveNow.data?.results?.[0]?.value ?? null)}
        />
      </div>

      <Panel title={t("overview.trend")}>
        <TimeseriesChart
          rows={webTrend.data?.results}
          secondaryRows={apiTrend.data?.results}
          seriesLabel={t("metric.pageviews")}
          secondaryLabel={t("metric.api_requests")}
          granularity={granularity}
        />
      </Panel>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel
          title={t("home.recentAlerts")}
          actions={
            <Link
              to={{ pathname: `/p/${projectId}/alerts`, search }}
              className="text-xs text-ink-soft hover:text-flame"
            >
              {t("overview.seeAll")}
            </Link>
          }
        >
          {projectAlerts.length === 0 ? (
            <p className="py-6 text-center text-sm text-ink-soft">{t("overview.noAlerts")}</p>
          ) : (
            <div className="space-y-1.5">
              {projectAlerts.map((event) => (
                <Link
                  key={event.id}
                  to={{ pathname: `/p/${projectId}/alerts`, search }}
                  className="flex flex-wrap items-center gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm hover:border-flame"
                >
                  <AlertEventRow event={event} />
                </Link>
              ))}
            </div>
          )}
        </Panel>
        <Panel
          title={t("overview.recentAnnotations")}
          actions={
            <Link
              to={{ pathname: `/p/${projectId}/annotations`, search }}
              className="text-xs text-ink-soft hover:text-flame"
            >
              {t("overview.seeAll")}
            </Link>
          }
        >
          {recentAnnotations.length === 0 ? (
            <p className="py-6 text-center text-sm text-ink-soft">{t("overview.noAnnotations")}</p>
          ) : (
            <ul className="space-y-1.5">
              {recentAnnotations.map((annotation) => (
                <li
                  key={annotation.id}
                  className="flex flex-wrap items-baseline gap-2 rounded-lg border border-line bg-surface px-3 py-2 text-sm"
                >
                  <span className="rounded-full bg-flame-soft px-2 py-0.5 text-[11px] font-semibold text-flame">
                    {t(`annotationsView.kind.${annotation.kind}`)}
                  </span>
                  <span className="flex-1">{annotation.text}</span>
                  <span className="tnum text-xs text-ink-soft">
                    {new Date(annotation.happened_at).toLocaleDateString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {SHORTCUTS.map(({ key, path }) => (
          <Link
            key={key}
            to={{ pathname: `/p/${projectId}/${path}`, search }}
            className="rise rounded-xl border border-line bg-surface px-4 py-3 text-sm font-semibold hover:border-flame hover:text-flame"
          >
            {t(`nav.${key}`)} <span aria-hidden>→</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

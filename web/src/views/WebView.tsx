import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import Choropleth, { countryValues } from "../components/Choropleth";
import TimeseriesChart from "../components/TimeseriesChart";

import IntegrateEmptyState from "../components/IntegrateEmptyState";
import { Panel, RankedTable, ScreenSubtitle, StatCard, Tabs } from "../components/widgets";
import { listAnnotations, type QueryFilter } from "../lib/api";
import { formatBucket, formatDuration, formatNumber, formatPercent } from "../lib/format";
import { compareScalar, scalar, useMetric } from "../lib/useMetric";
import { useDashboard, type TrafficClass } from "../lib/state";

const TRAFFIC_CLASSES: TrafficClass[] = ["all", "human", "bot", "ai_agent"];
const UTM_TABS = ["utm_source", "utm_medium", "utm_campaign"] as const;
const DEVICE_TABS = ["browser", "os", "device"] as const;
const AUDIENCE_TABS = ["locale", "asn"] as const;
const GEO_LEVELS = ["country", "region", "city"] as const;
type GeoLevel = (typeof GEO_LEVELS)[number];

function TrafficClassFilter() {
  const { t } = useTranslation();
  const { trafficClass, setTrafficClass } = useDashboard();
  return (
    <div className="flex gap-1" role="group" aria-label={t("trafficClass.label")}>
      {TRAFFIC_CLASSES.map((klass) => (
        <button
          key={klass}
          onClick={() => setTrafficClass(klass)}
          className={`rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors ${
            trafficClass === klass
              ? "border-flame bg-flame text-white"
              : "border-line text-ink-soft hover:border-flame hover:text-flame"
          }`}
        >
          {t(`trafficClass.${klass}`)}
        </button>
      ))}
    </div>
  );
}

function StatRow({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const visitors = useMetric({ metric: "visitors", projectId });
  const pageviews = useMetric({ metric: "pageviews", projectId });
  const sessions = useMetric({ metric: "sessions", projectId });
  const bounce = useMetric({ metric: "bounce_rate", projectId });
  const duration = useMetric({ metric: "session_duration", projectId });

  const card = (
    query: ReturnType<typeof useMetric>,
    term: string,
    format: (value: number | null) => string,
    inverse = false,
    note?: string,
  ) => (
    <StatCard
      term={term}
      value={format(scalar(query.data))}
      compareValue={
        query.data?.compare_results
          ? { current: scalar(query.data), previous: compareScalar(query.data) }
          : undefined
      }
      inverse={inverse}
      note={note}
    />
  );

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {card(visitors, "visitors", formatNumber, false, t("metric.visitDaysNote"))}
      {card(pageviews, "pageviews", formatNumber)}
      {card(sessions, "sessions", formatNumber)}
      {card(bounce, "bounce_rate", formatPercent, true)}
      {card(duration, "session_duration", formatDuration)}
    </div>
  );
}

/** Geography (issue #50): an embedded-basemap choropleth where clicking a
 *  country cross-filters the WHOLE dashboard (the filter lives in the URL),
 *  plus a country → region → city drill-down table beside it. */
function GeoPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const { geo, setGeo } = useDashboard();
  const level: GeoLevel = geo.region ? "city" : geo.country ? "region" : "country";

  // the map always shows every country — it must not be filtered by the
  // very country it selects (the drill table, like the rest, is)
  const mapQuery = useMetric({
    metric: "visitors",
    dimensions: ["country"],
    projectId,
    ignoreGeo: true,
  });
  const tableQuery = useMetric({
    metric: "visitors",
    dimensions: [level],
    projectId,
    keepPreviousData: false,
  });

  const values = countryValues(mapQuery.data?.results);

  const crumbs = [
    { label: t("web.worldTotal"), onClick: () => setGeo(null, null) },
    ...(geo.country
      ? [{ label: geo.country, onClick: () => setGeo(geo.country, null) }]
      : []),
    ...(geo.region ? [{ label: geo.region, onClick: () => undefined }] : []),
  ];

  return (
    <Panel
      title={t("web.geo")}
      className="md:col-span-2"
      actions={
        <nav className="flex items-center gap-1 text-xs text-ink-soft">
          {crumbs.map((crumb, index) => (
            <span key={crumb.label} className="flex items-center gap-1">
              {index > 0 && <span aria-hidden>›</span>}
              <button onClick={crumb.onClick} className="hover:text-flame">
                {crumb.label}
              </button>
            </span>
          ))}
        </nav>
      }
    >
      <div className="grid gap-4 md:grid-cols-[2fr_1fr]">
        <Choropleth
          values={values}
          selected={geo.country}
          onSelect={(a2) => setGeo(a2 === geo.country ? null : a2, null)}
          formatValue={formatNumber}
          legendLabel={t("metric.visitors")}
        />
        <RankedTable
          rows={tableQuery.data?.results}
          dimension={level}
          onRowClick={
            level === "city"
              ? undefined
              : (raw) =>
                  raw &&
                  (level === "country" ? setGeo(raw, null) : setGeo(geo.country, raw))
          }
        />
      </div>
    </Panel>
  );
}

function AiVisibilityPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const aiFilter: QueryFilter[] = [
    { dimension: "traffic_class", op: "eq", value: "ai_agent" },
  ];
  const shares = useMetric({
    metric: "pageviews",
    dimensions: ["traffic_class"],
    projectId,
    projectOnly: true,
  });
  const agents = useMetric({
    metric: "pageviews",
    dimensions: ["class_reason"],
    extraFilters: aiFilter,
    projectId,
    projectOnly: true,
  });
  const pages = useMetric({
    metric: "pageviews",
    dimensions: ["page"],
    extraFilters: aiFilter,
    projectId,
    projectOnly: true,
  });

  const total = (shares.data?.results ?? []).reduce((sum, row) => sum + (row.value ?? 0), 0);

  return (
    <Panel title={t("aiVisibility.title")} className="md:col-span-2">
      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <h3 className="mb-1 text-xs uppercase tracking-wide text-ink-soft">
            {t("aiVisibility.shares")}
          </h3>
          {(shares.data?.results ?? []).map((row) => {
            const klass = String(row.traffic_class ?? "");
            const pct = total > 0 ? ((row.value ?? 0) / total) * 100 : 0;
            return (
              <div key={klass} className="mb-1 flex items-center gap-2 text-xs">
                <span className="w-20 truncate">{t(`trafficClass.${klass}`)}</span>
                <div className="h-3 flex-1 overflow-hidden rounded bg-flame-soft">
                  <div className="h-full bg-flame" style={{ width: `${pct}%` }} />
                </div>
                <span className="w-10 text-right tabular-nums">{Math.round(pct)}%</span>
              </div>
            );
          })}
          {total === 0 && <p className="text-xs text-ink-soft">{t("web.empty")}</p>}
        </div>
        <div>
          <h3 className="mb-1 text-xs uppercase tracking-wide text-ink-soft">
            {t("aiVisibility.agents")}
          </h3>
          <RankedTable
            rows={agents.data?.results.map((row) => ({
              ...row,
              class_reason: String(row.class_reason ?? "").replace(/^ua:/, ""),
            }))}
            dimension="class_reason"
          />
        </div>
        <div>
          <h3 className="mb-1 text-xs uppercase tracking-wide text-ink-soft">
            {t("aiVisibility.pages")}
          </h3>
          <RankedTable rows={pages.data?.results} dimension="page" />
        </div>
      </div>
    </Panel>
  );
}

const VITALS = [
  { key: "lcp", metric: "web_vital_lcp_p75", unit: "ms", good: 2500, poor: 4000 },
  { key: "cls", metric: "web_vital_cls_p75", unit: "", good: 0.1, poor: 0.25 },
  { key: "inp", metric: "web_vital_inp_p75", unit: "ms", good: 200, poor: 500 },
  { key: "ttfb", metric: "web_vital_ttfb_p75", unit: "ms", good: 800, poor: 1800 },
] as const;

function VitalsPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const lcp = useMetric({ metric: "web_vital_lcp_p75", projectId, projectOnly: true });
  const cls = useMetric({ metric: "web_vital_cls_p75", projectId, projectOnly: true });
  const inp = useMetric({ metric: "web_vital_inp_p75", projectId, projectOnly: true });
  const ttfb = useMetric({ metric: "web_vital_ttfb_p75", projectId, projectOnly: true });
  const queries = { lcp, cls, inp, ttfb };

  return (
    <Panel title={t("vitals.title")} className="md:col-span-2">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {VITALS.map((vital) => {
          const value = scalar(queries[vital.key].data);
          const state =
            value === null ? "none" : value <= vital.good ? "good" : value <= vital.poor ? "ni" : "poor";
          const dot =
            state === "good" ? "bg-emerald-500" : state === "ni" ? "bg-amber-500" : "bg-flame";
          return (
            <div key={vital.key} className="rounded-lg border border-line bg-surface p-3">
              <div className="flex items-center gap-1.5 text-xs uppercase tracking-wide text-ink-soft">
                {state !== "none" && <span className={`h-2 w-2 rounded-full ${dot}`} />}
                {vital.key.toUpperCase()}
                <span className="normal-case">· p75</span>
              </div>
              <div className="tnum mt-1 font-display text-xl font-bold">
                {value === null ? "—" : `${formatNumber(value)}${vital.unit ? ` ${vital.unit}` : ""}`}
              </div>
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-[11px] text-ink-soft">{t("vitals.note")}</p>
    </Panel>
  );
}

export default function WebView() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams();
  const { granularity } = useDashboard();
  const [utmTab, setUtmTab] = useState<(typeof UTM_TABS)[number]>("utm_source");
  const [deviceTab, setDeviceTab] = useState<(typeof DEVICE_TABS)[number]>("browser");
  const [audienceTab, setAudienceTab] = useState<(typeof AUDIENCE_TABS)[number]>("locale");
  const audience = useMetric({ metric: "visitors", dimensions: [audienceTab], projectId });

  const timeseries = useMetric({
    metric: "visitors",
    withGranularity: true,
    projectId,
  });
  const { period } = useDashboard();
  const annotations = useQuery({
    queryKey: ["annotations", projectId, period],
    queryFn: () => listAnnotations(projectId, period),
  });
  const annotationMarks = (annotations.data ?? []).map((annotation) => ({
    bucket: formatBucket(annotation.happened_at, granularity),
    label: annotation.text,
  }));
  const pages = useMetric({ metric: "visitors", dimensions: ["page"], projectId });
  const referrers = useMetric({ metric: "visitors", dimensions: ["referrer"], projectId });
  const utm = useMetric({ metric: "visitors", dimensions: [utmTab], projectId });
  const devices = useMetric({ metric: "visitors", dimensions: [deviceTab], projectId });
  const events = useMetric({
    metric: "custom_events",
    dimensions: ["event_name"],
    projectId,
  });

  // "no data" means the project, not the current filters: the probe ignores
  // traffic class and geo so a filtered-out view never claims "instrument me"
  const probe = useMetric({ metric: "pageviews", projectId, projectOnly: true });
  const webEmpty = probe.data !== undefined && (scalar(probe.data) ?? 0) === 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-xl font-bold tracking-tight">{t("web.title")}</h1>
        <TrafficClassFilter />
      </div>
      <ScreenSubtitle id="web" />

      {webEmpty && <IntegrateEmptyState projectId={projectId} type="web" />}

      <StatRow projectId={projectId} />

      <Panel title={t("web.timeseries")}>
        <TimeseriesChart
          rows={timeseries.data?.results}
          compareRows={timeseries.data?.compare_results}
          granularity={granularity}
          annotations={annotationMarks}
        />
      </Panel>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title={t("web.topPages")}>
          <RankedTable rows={pages.data?.results} dimension="page" />
        </Panel>
        <Panel title={t("web.topReferrers")}>
          <RankedTable rows={referrers.data?.results} dimension="referrer" />
        </Panel>
        <Panel
          title={t("web.utm")}
          actions={
            <Tabs
              value={utmTab}
              options={UTM_TABS}
              onChange={setUtmTab}
              labelFor={(tab) => t(`web.${tab}`)}
            />
          }
        >
          <RankedTable rows={utm.data?.results} dimension={utmTab} />
        </Panel>
        <GeoPanel projectId={projectId} />
        <Panel title={t("web.topEvents")}>
          <RankedTable rows={events.data?.results} dimension="event_name" />
        </Panel>
        <Panel
          title={t("web.devices")}
          actions={
            <Tabs
              value={deviceTab}
              options={DEVICE_TABS}
              onChange={setDeviceTab}
              labelFor={(tab) => t(`web.${tab}`)}
            />
          }
        >
          <RankedTable rows={devices.data?.results} dimension={deviceTab} />
        </Panel>
        <Panel
          title={t("web.audience")}
          actions={
            <Tabs
              value={audienceTab}
              options={AUDIENCE_TABS}
              onChange={setAudienceTab}
              labelFor={(tab) => t(`web.${tab}`)}
            />
          }
        >
          <RankedTable rows={audience.data?.results} dimension={audienceTab} />
        </Panel>
        <AiVisibilityPanel projectId={projectId} />
        <VitalsPanel projectId={projectId} />
      </div>
    </div>
  );
}

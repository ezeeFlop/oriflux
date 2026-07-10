import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import TimeseriesChart from "../components/TimeseriesChart";
import { PeriodPicker } from "../components/Shell";
import { Panel, RankedTable, StatCard, Tabs } from "../components/widgets";
import type { QueryFilter } from "../lib/api";
import { formatDuration, formatNumber, formatPercent } from "../lib/format";
import { compareScalar, scalar, useMetric } from "../lib/useMetric";
import { useDashboard, type TrafficClass } from "../lib/state";

const TRAFFIC_CLASSES: TrafficClass[] = ["all", "human", "bot", "ai_agent"];
const UTM_TABS = ["utm_source", "utm_medium", "utm_campaign"] as const;
const DEVICE_TABS = ["browser", "os", "device"] as const;
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
    label: string,
    format: (value: number | null) => string,
    inverse = false,
    note?: string,
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
      note={note}
    />
  );

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {card(visitors, t("metric.visitors"), formatNumber, false, t("metric.visitDaysNote"))}
      {card(pageviews, t("metric.pageviews"), formatNumber)}
      {card(sessions, t("metric.sessions"), formatNumber)}
      {card(bounce, t("metric.bounce_rate"), formatPercent, true)}
      {card(duration, t("metric.session_duration"), formatDuration)}
    </div>
  );
}

function GeoPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const [path, setPath] = useState<{ country?: string; region?: string }>({});
  const level: GeoLevel = path.region ? "city" : path.country ? "region" : "country";
  const extraFilters: QueryFilter[] = [];
  if (path.country) extraFilters.push({ dimension: "country", op: "eq", value: path.country });
  if (path.region) extraFilters.push({ dimension: "region", op: "eq", value: path.region });

  const query = useMetric({ metric: "visitors", dimensions: [level], extraFilters, projectId });

  const crumbs = [
    { label: t("web.worldTotal"), onClick: () => setPath({}) },
    ...(path.country
      ? [{ label: path.country, onClick: () => setPath({ country: path.country }) }]
      : []),
    ...(path.region ? [{ label: path.region, onClick: () => undefined }] : []),
  ];

  return (
    <Panel
      title={t("web.geo")}
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
      <RankedTable
        rows={query.data?.results}
        dimension={level}
        onRowClick={
          level === "city"
            ? undefined
            : (raw) =>
                raw &&
                setPath(level === "country" ? { country: raw } : { ...path, region: raw })
        }
      />
    </Panel>
  );
}

export default function WebView() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams();
  const { granularity } = useDashboard();
  const [utmTab, setUtmTab] = useState<(typeof UTM_TABS)[number]>("utm_source");
  const [deviceTab, setDeviceTab] = useState<(typeof DEVICE_TABS)[number]>("browser");

  const timeseries = useMetric({
    metric: "visitors",
    withGranularity: true,
    projectId,
  });
  const pages = useMetric({ metric: "visitors", dimensions: ["page"], projectId });
  const referrers = useMetric({ metric: "visitors", dimensions: ["referrer"], projectId });
  const utm = useMetric({ metric: "visitors", dimensions: [utmTab], projectId });
  const devices = useMetric({ metric: "visitors", dimensions: [deviceTab], projectId });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="font-display text-xl font-bold tracking-tight">{t("web.title")}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <TrafficClassFilter />
          <PeriodPicker />
        </div>
      </div>

      <StatRow projectId={projectId} />

      <Panel title={t("web.timeseries")}>
        <TimeseriesChart
          rows={timeseries.data?.results}
          compareRows={timeseries.data?.compare_results}
          granularity={granularity}
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
          className="md:col-span-2"
        >
          <RankedTable rows={devices.data?.results} dimension={deviceTab} />
        </Panel>
      </div>
    </div>
  );
}

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import TimeseriesChart from "../components/TimeseriesChart";
import { PeriodPicker } from "../components/Shell";
import { Panel, RankedTable, StatCard, Tabs } from "../components/widgets";
import {
  createGoal,
  deleteGoal,
  listGoals,
  runFunnel,
  runRetention,
  type FunnelStep,
  type QueryFilter,
} from "../lib/api";
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

function GoalsPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const { period } = useDashboard();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [kind, setKind] = useState<"event" | "page">("page");
  const [target, setTarget] = useState("");
  const [error, setError] = useState("");

  const goals = useQuery({
    queryKey: ["goals", projectId, period],
    queryFn: () => listGoals(projectId, period),
  });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["goals", projectId] });
  const create = useMutation({
    mutationFn: () => createGoal(projectId, { name, kind, target }),
    onSuccess: () => {
      setName("");
      setTarget("");
      setError("");
      invalidate();
    },
    onError: () => setError(t("goals.error")),
  });
  const remove = useMutation({ mutationFn: deleteGoal, onSuccess: invalidate });

  return (
    <Panel title={t("goals.title")} className="md:col-span-2">
      {goals.data && goals.data.length > 0 ? (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-ink-soft">
              <th className="py-1 font-medium">{t("goals.name")}</th>
              <th className="py-1 font-medium">{t("goals.target")}</th>
              <th className="py-1 text-right font-medium">{t("goals.conversions")}</th>
              <th className="py-1 text-right font-medium">{t("goals.rate")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {goals.data.map((goal) => (
              <tr key={goal.id} className="border-t border-line">
                <td className="py-1.5 font-medium">{goal.name}</td>
                <td className="py-1.5 text-ink-soft">
                  <span className="mr-1 rounded bg-flame-soft px-1 text-[10px] uppercase text-flame">
                    {t(`goals.${goal.kind}`)}
                  </span>
                  {goal.target}
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {goal.conversions === null ? "—" : formatNumber(goal.conversions)}
                </td>
                <td className="py-1.5 text-right tabular-nums">
                  {goal.conversion_rate === null ? "—" : formatPercent(goal.conversion_rate)}
                </td>
                <td className="py-1.5 text-right">
                  <button
                    onClick={() => remove.mutate(goal.id)}
                    aria-label={t("goals.delete")}
                    className="text-xs text-ink-soft hover:text-flame"
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="py-2 text-sm text-ink-soft">{t("goals.empty")}</p>
      )}

      <form
        className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3"
        onSubmit={(event) => {
          event.preventDefault();
          if (name && target) create.mutate();
        }}
      >
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t("goals.name")}
          className="w-36 rounded-md border border-line bg-surface px-2 py-1 text-xs"
        />
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value as "event" | "page")}
          aria-label={t("goals.kind")}
          className="rounded-md border border-line bg-surface px-2 py-1 text-xs"
        >
          <option value="page">{t("goals.page")}</option>
          <option value="event">{t("goals.event")}</option>
        </select>
        <input
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          placeholder={kind === "page" ? "/pricing" : "signup_completed"}
          className="w-44 rounded-md border border-line bg-surface px-2 py-1 text-xs font-mono"
        />
        <button
          type="submit"
          disabled={!name || !target || create.isPending}
          className="rounded-md bg-flame px-2.5 py-1 text-xs font-semibold text-white disabled:opacity-40"
        >
          {t("goals.add")}
        </button>
        {error && <span className="text-xs text-flame">{error}</span>}
      </form>
    </Panel>
  );
}

function FunnelPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const { period } = useDashboard();
  const [steps, setSteps] = useState<FunnelStep[]>([
    { kind: "page", target: "/" },
    { kind: "event", target: "" },
  ]);
  const [scope, setScope] = useState<"session" | "identified">("session");

  const ready = steps.length >= 2 && steps.every((s) => s.target.trim().length > 0);
  const funnel = useQuery({
    queryKey: ["funnel", projectId, steps, scope, period],
    queryFn: () => runFunnel({ steps, scope, project_id: projectId, period }),
    enabled: ready,
  });

  const setStep = (index: number, patch: Partial<FunnelStep>) =>
    setSteps((current) =>
      current.map((step, i) => (i === index ? { ...step, ...patch } : step)),
    );
  const max = Math.max(1, ...(funnel.data?.steps.map((s) => s.entered) ?? [1]));

  return (
    <Panel
      title={t("funnel.title")}
      className="md:col-span-2"
      actions={
        <div className="flex items-center gap-2">
          <span className="rounded bg-flame-soft px-1.5 py-0.5 text-[10px] uppercase text-flame">
            {t(`funnel.${scope}`)}
          </span>
          <select
            value={scope}
            onChange={(e) => setScope(e.target.value as "session" | "identified")}
            aria-label={t("funnel.scope")}
            className="rounded-md border border-line bg-surface px-2 py-1 text-xs"
          >
            <option value="session">{t("funnel.sessionOption")}</option>
            <option value="identified">{t("funnel.identifiedOption")}</option>
          </select>
        </div>
      }
    >
      <div className="space-y-1.5">
        {steps.map((step, index) => (
          <div key={index} className="flex items-center gap-2">
            <span className="w-4 text-xs tabular-nums text-ink-soft">{index + 1}.</span>
            <select
              value={step.kind}
              onChange={(e) => setStep(index, { kind: e.target.value as "event" | "page" })}
              className="rounded-md border border-line bg-surface px-2 py-1 text-xs"
            >
              <option value="page">{t("goals.page")}</option>
              <option value="event">{t("goals.event")}</option>
            </select>
            <input
              value={step.target}
              onChange={(e) => setStep(index, { target: e.target.value })}
              placeholder={step.kind === "page" ? "/pricing" : "signup_completed"}
              className="w-48 rounded-md border border-line bg-surface px-2 py-1 text-xs font-mono"
            />
            {funnel.data?.steps[index] && (
              <div className="flex flex-1 items-center gap-2">
                <div className="h-4 flex-1 overflow-hidden rounded bg-flame-soft">
                  <div
                    className="h-full rounded bg-flame transition-all"
                    style={{ width: `${(funnel.data.steps[index].entered / max) * 100}%` }}
                  />
                </div>
                <span className="w-14 text-right text-xs tabular-nums">
                  {formatNumber(funnel.data.steps[index].entered)}
                </span>
              </div>
            )}
            {steps.length > 2 && (
              <button
                onClick={() => setSteps((c) => c.filter((_, i) => i !== index))}
                aria-label={t("funnel.removeStep")}
                className="text-xs text-ink-soft hover:text-flame"
              >
                ✕
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="mt-2 flex items-center justify-between">
        <button
          onClick={() => setSteps((c) => [...c, { kind: "page", target: "" }])}
          disabled={steps.length >= 8}
          className="text-xs font-medium text-flame hover:underline disabled:opacity-40"
        >
          + {t("funnel.addStep")}
        </button>
        {funnel.data && (
          <span className="text-xs text-ink-soft">
            {t("funnel.conversion")}{" "}
            <strong className="text-ink">{formatPercent(funnel.data.conversion_rate)}</strong>
          </span>
        )}
      </div>
      {scope === "session" && (
        <p className="mt-1 text-[11px] text-ink-soft">{t("funnel.sessionNote")}</p>
      )}
    </Panel>
  );
}

function RetentionPanel({ projectId }: { projectId: string }) {
  const { t } = useTranslation();
  const { period } = useDashboard();
  const [activation, setActivation] = useState("signup_completed");
  const [granularity, setGranularity] = useState<"week" | "month">("week");

  const valid = /^[a-z][a-z0-9_]{0,63}$/.test(activation);
  const retention = useQuery({
    queryKey: ["retention", projectId, activation, granularity, period],
    queryFn: () =>
      runRetention({ activation_event: activation, granularity, project_id: projectId, period }),
    enabled: valid,
  });

  const cohorts = new Map<string, Map<number, number>>();
  let maxOffset = 0;
  for (const row of retention.data?.cohorts ?? []) {
    if (!cohorts.has(row.cohort_start)) cohorts.set(row.cohort_start, new Map());
    cohorts.get(row.cohort_start)!.set(row.offset, row.users);
    maxOffset = Math.max(maxOffset, row.offset);
  }
  const offsets = Array.from({ length: maxOffset + 1 }, (_, i) => i);

  return (
    <Panel
      title={t("retention.title")}
      className="md:col-span-2"
      actions={
        <div className="flex items-center gap-2">
          <input
            value={activation}
            onChange={(e) => setActivation(e.target.value)}
            aria-label={t("retention.activation")}
            className="w-44 rounded-md border border-line bg-surface px-2 py-1 text-xs font-mono"
          />
          <select
            value={granularity}
            onChange={(e) => setGranularity(e.target.value as "week" | "month")}
            className="rounded-md border border-line bg-surface px-2 py-1 text-xs"
          >
            <option value="week">{t("retention.weekly")}</option>
            <option value="month">{t("retention.monthly")}</option>
          </select>
        </div>
      }
    >
      {cohorts.size > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left uppercase tracking-wide text-ink-soft">
                <th className="py-1 pr-2 font-medium">{t("retention.cohort")}</th>
                {offsets.map((offset) => (
                  <th key={offset} className="px-1 py-1 text-center font-medium">
                    +{offset}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Array.from(cohorts.entries()).map(([start, cells]) => {
                const size = cells.get(0) ?? 0;
                return (
                  <tr key={start} className="border-t border-line">
                    <td className="whitespace-nowrap py-1 pr-2 tabular-nums">
                      {start.slice(0, 10)}
                      <span className="ml-1 text-ink-soft">({size})</span>
                    </td>
                    {offsets.map((offset) => {
                      const users = cells.get(offset);
                      const pct = users === undefined || size === 0 ? null : (users / size) * 100;
                      return (
                        <td key={offset} className="px-0.5 py-0.5 text-center">
                          {pct === null ? (
                            <span className="text-ink-soft">·</span>
                          ) : (
                            <span
                              className="block rounded px-1 py-0.5 tabular-nums"
                              style={{
                                backgroundColor: `rgba(214, 69, 36, ${0.08 + 0.6 * (pct / 100)})`,
                                color: pct > 55 ? "white" : undefined,
                              }}
                            >
                              {Math.round(pct)}%
                            </span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="py-2 text-sm text-ink-soft">{t("retention.empty")}</p>
      )}
      <p className="mt-1 text-[11px] text-ink-soft">{t("retention.identifiedNote")}</p>
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
  const events = useMetric({
    metric: "custom_events",
    dimensions: ["event_name"],
    projectId,
  });

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
        <GoalsPanel projectId={projectId} />
        <FunnelPanel projectId={projectId} />
        <RetentionPanel projectId={projectId} />
      </div>
    </div>
  );
}

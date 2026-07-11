/** Funnels & retention view (issue #49): rehomed from the old WebView.
 *  The privacy constraints stay on-screen — multi-day funnels and retention
 *  are identified-users-only by design (PRD §5.2). */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { Panel } from "../components/widgets";
import { runFunnel, runRetention, type FunnelStep } from "../lib/api";
import { formatNumber, formatPercent } from "../lib/format";
import { useDashboard } from "../lib/state";

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


export default function ProductView() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams();
  return (
    <div className="space-y-4">
      <h1 className="font-display text-xl font-bold tracking-tight">{t("nav.product")}</h1>
      <FunnelPanel projectId={projectId} />
      <RetentionPanel projectId={projectId} />
    </div>
  );
}

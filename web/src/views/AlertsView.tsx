/** Alerts screen (issue #52): rule CRUD on the existing endpoints plus the
 *  event feed. Rules are org resources scoped by a project_id filter — this
 *  view shows the current project's rules and org-wide ones, and creates
 *  rules pre-filtered on the current project. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import AlertEventRow from "../components/AlertEventRow";
import { FIELD, Panel, PRIMARY_BUTTON } from "../components/widgets";
import {
  createAlertRule,
  deleteAlertRule,
  listAlertEvents,
  listAlertRules,
  patchAlertRule,
  type AlertRule,
} from "../lib/api";
import { useDashboard } from "../lib/state";


/** metrics that make sense as thresholds — all registry names */
const ALERT_METRICS = [
  "visitors",
  "pageviews",
  "sessions",
  "api_requests",
  "api_error_rate_4xx",
  "api_error_rate_5xx",
  "api_latency_p95",
] as const;

function ruleTargetsProject(rule: AlertRule, projectId: string): boolean {
  const projectFilter = rule.filters.find((f) => f.dimension === "project_id");
  return projectFilter === undefined || projectFilter.value === projectId;
}

function RulesPanel({ orgId, projectId }: { orgId: string; projectId: string }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [metric, setMetric] = useState<string>("api_error_rate_5xx");
  const [condition, setCondition] = useState<"gt" | "lt">("gt");
  const [threshold, setThreshold] = useState("5");
  const [windowMinutes, setWindowMinutes] = useState("5");

  const rules = useQuery({
    queryKey: ["alert-rules", orgId],
    queryFn: () => listAlertRules(orgId),
  });

  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: ["alert-rules", orgId] });

  const create = useMutation({
    mutationFn: () =>
      createAlertRule(orgId, {
        name,
        metric,
        filters: [{ dimension: "project_id", op: "eq", value: projectId }],
        condition,
        threshold: Number(threshold),
        window_minutes: Number(windowMinutes),
      }),
    onSuccess: () => {
      setName("");
      invalidate();
    },
  });

  const [editing, setEditing] = useState<{ id: string; name: string; threshold: string } | null>(
    null,
  );
  const edit = useMutation({
    mutationFn: () =>
      patchAlertRule((editing as { id: string }).id, {
        name: (editing as { name: string }).name,
        threshold: Number((editing as { threshold: string }).threshold),
      }),
    onSuccess: () => {
      setEditing(null);
      invalidate();
    },
  });

  const toggle = useMutation({
    mutationFn: (rule: AlertRule) => patchAlertRule(rule.id, { enabled: !rule.enabled }),
    onSuccess: invalidate,
  });

  const remove = useMutation({ mutationFn: deleteAlertRule, onSuccess: invalidate });

  const visible = (rules.data ?? []).filter((rule) => ruleTargetsProject(rule, projectId));

  return (
    <Panel title={t("alerts.rules")}>
      <ul className="divide-y divide-line/60">
        {visible.map((rule) => (
          <li key={rule.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase ${
                rule.enabled ? "bg-flame-soft text-flame" : "border border-line text-ink-soft"
              }`}
            >
              {rule.enabled ? t("alerts.active") : t("alerts.paused")}
            </span>
            {editing?.id === rule.id ? (
              <form
                className="flex min-w-0 flex-1 flex-wrap items-center gap-2"
                onSubmit={(event) => {
                  event.preventDefault();
                  edit.mutate();
                }}
              >
                <input
                  value={editing.name}
                  onChange={(event) => setEditing({ ...editing, name: event.target.value })}
                  aria-label={t("alerts.ruleName")}
                  className={`min-w-0 flex-1 ${FIELD}`}
                />
                <input
                  type="number"
                  step="any"
                  value={editing.threshold}
                  onChange={(event) => setEditing({ ...editing, threshold: event.target.value })}
                  aria-label={t("alerts.threshold")}
                  className={`w-24 ${FIELD}`}
                />
                <button type="submit" className={PRIMARY_BUTTON}>
                  {t("alerts.save")}
                </button>
              </form>
            ) : (
              <>
                <strong className="min-w-0 flex-1 truncate">{rule.name}</strong>
                <span className="text-ink-soft">
                  {t(`metric.${rule.metric}`)} {rule.condition === "gt" ? ">" : "<"}{" "}
                  <span className="tnum">{rule.threshold}</span> / {rule.window_minutes} min
                </span>
              </>
            )}
            <button
              onClick={() =>
                setEditing(
                  editing?.id === rule.id
                    ? null
                    : { id: rule.id, name: rule.name, threshold: String(rule.threshold) },
                )
              }
              aria-label={t("alerts.edit")}
              className="rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-soft hover:border-flame hover:text-flame"
            >
              ✎
            </button>
            <button
              onClick={() => toggle.mutate(rule)}
              className="rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-soft hover:border-flame hover:text-flame"
            >
              {rule.enabled ? t("alerts.pause") : t("alerts.resume")}
            </button>
            <button
              onClick={() => remove.mutate(rule.id)}
              aria-label={t("alerts.delete")}
              className="rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-soft hover:border-down hover:text-down"
            >
              ✕
            </button>
          </li>
        ))}
        {rules.data && visible.length === 0 && (
          <li className="py-3 text-sm text-ink-soft">{t("alerts.noRules")}</li>
        )}
      </ul>
      <form
        className="mt-3 flex flex-wrap items-center gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          create.mutate();
        }}
      >
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("alerts.ruleName")}
          aria-label={t("alerts.ruleName")}
          className={`min-w-0 flex-1 ${FIELD}`}
        />
        <select
          value={metric}
          onChange={(event) => setMetric(event.target.value)}
          aria-label={t("alerts.metric")}
          className={FIELD}
        >
          {ALERT_METRICS.map((option) => (
            <option key={option} value={option}>
              {t(`metric.${option}`)}
            </option>
          ))}
        </select>
        <select
          value={condition}
          onChange={(event) => setCondition(event.target.value as "gt" | "lt")}
          aria-label={t("alerts.condition")}
          className={FIELD}
        >
          <option value="gt">&gt;</option>
          <option value="lt">&lt;</option>
        </select>
        <input
          type="number"
          step="any"
          value={threshold}
          onChange={(event) => setThreshold(event.target.value)}
          aria-label={t("alerts.threshold")}
          className={`w-24 ${FIELD}`}
        />
        <label className="flex items-center gap-1 text-xs text-ink-soft">
          <input
            type="number"
            min="1"
            max="1440"
            value={windowMinutes}
            onChange={(event) => setWindowMinutes(event.target.value)}
            aria-label={t("alerts.window")}
            className={`w-20 ${FIELD}`}
          />
          min
        </label>
        <button type="submit" disabled={name.trim() === ""} className={PRIMARY_BUTTON}>
          {t("alerts.create")}
        </button>
      </form>
      {create.isError && <p className="mt-2 text-xs text-down">{t("alerts.createFailed")}</p>}
    </Panel>
  );
}

function EventsPanel({ orgId, projectId }: { orgId: string; projectId: string }) {
  const { t } = useTranslation();
  const events = useQuery({
    queryKey: ["alert-events", orgId],
    queryFn: () => listAlertEvents(orgId),
    refetchInterval: 60_000,
  });

  const visible = (events.data ?? []).filter(
    (event) => event.project_id === null || event.project_id === projectId,
  );

  return (
    <Panel title={t("alerts.events")}>
      <ul className="divide-y divide-line/60">
        {visible.map((event) => (
          <li key={event.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
            <AlertEventRow event={event} />
          </li>
        ))}
        {events.data && visible.length === 0 && (
          <li className="py-3 text-sm text-ink-soft">{t("alerts.noEvents")}</li>
        )}
      </ul>
      <p className="mt-2 text-[11px] text-ink-soft">{t("alerts.diagnosisNote")}</p>
    </Panel>
  );
}

export default function AlertsView() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams();
  const { orgId } = useDashboard();

  if (orgId === null) return null;

  return (
    <div className="space-y-4">
      <h1 className="font-display text-xl font-bold tracking-tight">{t("nav.alerts")}</h1>
      <RulesPanel orgId={orgId} projectId={projectId} />
      <EventsPanel orgId={orgId} projectId={projectId} />
    </div>
  );
}

/** Goals view (issue #49): rehomed from the old WebView into its own
 *  sidebar entry — same registry-backed conversions, same CRUD. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { Panel } from "../components/widgets";
import { createGoal, deleteGoal, listGoals } from "../lib/api";
import { formatNumber, formatPercent } from "../lib/format";
import { useDashboard } from "../lib/state";

export function GoalsPanel({ projectId }: { projectId: string }) {
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

export default function GoalsView() {
  const { t } = useTranslation();
  const { projectId = "" } = useParams();
  return (
    <div className="space-y-4">
      <h1 className="font-display text-xl font-bold tracking-tight">{t("goals.title")}</h1>
      <GoalsPanel projectId={projectId} />
    </div>
  );
}

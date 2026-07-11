/** Release annotations (issue #54): create and delete timeline marks from
 *  the UI — they already render as markers on the time-series charts. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";

import { FIELD, Panel, PRIMARY_BUTTON } from "../components/widgets";
import {
  createAnnotation,
  deleteAnnotation,
  listAnnotations,
  type Annotation,
} from "../lib/api";
import { useDashboard } from "../lib/state";


const KINDS: Annotation["kind"][] = ["release", "campaign", "incident", "note"];

export default function AnnotationsView() {
  const { t, i18n } = useTranslation();
  const { projectId = "" } = useParams();
  const { period } = useDashboard();
  const queryClient = useQueryClient();

  const [text, setText] = useState("");
  const [kind, setKind] = useState<Annotation["kind"]>("release");
  const [when, setWhen] = useState("");

  const annotations = useQuery({
    queryKey: ["annotations", projectId, period],
    queryFn: () => listAnnotations(projectId, period),
  });

  const invalidate = () =>
    void queryClient.invalidateQueries({ queryKey: ["annotations", projectId] });

  const create = useMutation({
    mutationFn: () =>
      createAnnotation(projectId, {
        kind,
        text,
        happened_at: when !== "" ? new Date(when).toISOString() : new Date().toISOString(),
      }),
    onSuccess: () => {
      setText("");
      setWhen("");
      invalidate();
    },
  });

  const remove = useMutation({ mutationFn: deleteAnnotation, onSuccess: invalidate });

  return (
    <div className="space-y-4">
      <h1 className="font-display text-xl font-bold tracking-tight">{t("nav.annotations")}</h1>
      <Panel title={t("annotationsView.inPeriod")}>
        <ul className="divide-y divide-line/60">
          {(annotations.data ?? []).map((annotation) => (
            <li key={annotation.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
              <span className="rounded-full border border-line px-2 py-0.5 text-[11px] font-semibold uppercase text-ink-soft">
                {t(`annotationsView.kind.${annotation.kind}`)}
              </span>
              <span className="min-w-0 flex-1 truncate">{annotation.text}</span>
              <span className="tnum text-xs text-ink-soft">
                {new Date(annotation.happened_at).toLocaleString(i18n.language)}
              </span>
              <button
                onClick={() => remove.mutate(annotation.id)}
                aria-label={t("annotationsView.delete")}
                className="rounded-md border border-line px-2 py-1 text-xs font-medium text-ink-soft hover:border-down hover:text-down"
              >
                ✕
              </button>
            </li>
          ))}
          {annotations.data && annotations.data.length === 0 && (
            <li className="py-3 text-sm text-ink-soft">{t("annotationsView.empty")}</li>
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
            value={text}
            onChange={(event) => setText(event.target.value)}
            placeholder={t("annotationsView.text")}
            aria-label={t("annotationsView.text")}
            className={`min-w-0 flex-1 ${FIELD}`}
          />
          <select
            value={kind}
            onChange={(event) => setKind(event.target.value as Annotation["kind"])}
            aria-label={t("annotationsView.kindLabel")}
            className={FIELD}
          >
            {KINDS.map((option) => (
              <option key={option} value={option}>
                {t(`annotationsView.kind.${option}`)}
              </option>
            ))}
          </select>
          <input
            type="datetime-local"
            value={when}
            onChange={(event) => setWhen(event.target.value)}
            aria-label={t("annotationsView.when")}
            className={FIELD}
          />
          <button type="submit" disabled={text.trim() === ""} className={PRIMARY_BUTTON}>
            {t("annotationsView.add")}
          </button>
        </form>
        <p className="mt-2 text-[11px] text-ink-soft">{t("annotationsView.chartNote")}</p>
      </Panel>
    </div>
  );
}

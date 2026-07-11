/** Ask Oriflux as a global ⌘K palette (issue #55). Every answer shows its
 *  numbers AND the typed query that produced them — the product constraint
 *  that AI answers always cite their source query. Opens on ⌘K / Ctrl+K,
 *  on the header button, or via the "oriflux:ask" window event. */

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import TimeseriesChart from "./TimeseriesChart";
import { ApiError, askOriflux, type AskResult, type QueryRow } from "../lib/api";

export function openAskPalette(): void {
  window.dispatchEvent(new CustomEvent("oriflux:ask"));
}

function isTimeSeries(rows: QueryRow[]): boolean {
  return rows.length > 1 && rows.every((row) => typeof row.bucket === "string");
}

export default function AskPalette() {
  const { t } = useTranslation();
  const { projectId } = useParams();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<AskResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
      if (event.key === "Escape") setOpen(false);
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("oriflux:ask", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("oriflux:ask", onOpen);
    };
  }, []);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      setResult(await askOriflux(question, projectId));
    } catch (err) {
      setResult(null);
      if (err instanceof ApiError && err.status === 503) setError(t("ask.disabled"));
      else if (err instanceof ApiError && err.status === 429) setError(t("ask.budget"));
      else if (err instanceof ApiError && err.status === 422) setError(t("ask.cannotCompile"));
      else setError(t("common.error"));
    } finally {
      setBusy(false);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-ink/40 px-4 pt-[12vh]"
      onClick={() => setOpen(false)}
    >
      <div
        role="dialog"
        aria-label={t("ask.title")}
        onClick={(event) => event.stopPropagation()}
        className="w-full max-w-2xl rounded-lg border border-line bg-surface-raised p-4 shadow-xl"
      >
        <form onSubmit={submit} className="flex items-center gap-2">
          <input
            ref={inputRef}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder={t("ask.placeholder")}
            aria-label={t("ask.title")}
            className="flex-1 rounded-md border border-line bg-surface px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={busy || !question.trim()}
            className="rounded-md bg-flame px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"
          >
            {busy ? "…" : t("ask.go")}
          </button>
        </form>
        <p className="mt-1 text-[11px] text-ink-soft">{t("ask.hint")}</p>
        {error && <p className="mt-2 text-sm text-down">{error}</p>}
        {result && (
          <div className="mt-3 space-y-3">
            {result.answer && <p className="text-sm">{result.answer}</p>}
            {isTimeSeries(result.results) && (
              <TimeseriesChart rows={result.results} granularity="day" />
            )}
            {!isTimeSeries(result.results) && result.results.length > 0 && (
              <table className="w-full text-xs">
                <tbody>
                  {result.results.slice(0, 12).map((row, index) => (
                    <tr key={index} className="border-t border-line">
                      {Object.entries(row).map(([key, value]) => (
                        <td key={key} className="tnum py-1 pr-3">
                          {String(value)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {/* transparency is not optional: the executed query is always shown */}
            <div>
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft">
                {t("ask.executedQuery")}
              </h3>
              <pre className="mt-1 max-h-48 overflow-auto rounded-md border border-line bg-paper p-2 text-[10px]">
                {JSON.stringify(result.query, null, 2)}
                {"\n\n"}
                {result.sql}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

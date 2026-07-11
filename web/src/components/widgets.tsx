/** Shared analytics widgets: stat cards, ranked breakdown tables, panels.
 *  Sober by design: numbers first, one accent, tabular figures. */

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { deltaPercent, formatNumber } from "../lib/format";
import type { QueryRow } from "../lib/api";

/** Shared form styling for the settings/alerts/annotations screens. */
export const PRIMARY_BUTTON =
  "rounded-md bg-flame px-3 py-1.5 text-sm font-semibold text-white hover:bg-flame-strong disabled:opacity-40";
export const FIELD = "rounded-md border border-line bg-surface px-2 py-1.5 text-sm";

export function Panel({
  title,
  children,
  actions,
  className = "",
}: {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`rise rounded-xl border border-line bg-surface p-4 shadow-[0_1px_2px_rgba(30,20,10,0.04)] ${className}`}
    >
      <header className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-sm font-semibold uppercase tracking-wide text-ink-soft">
          {title}
        </h2>
        {actions}
      </header>
      {children}
    </section>
  );
}

export function StatCard({
  label,
  value,
  compareValue,
  note,
  inverse = false,
}: {
  label: string;
  value: string;
  compareValue?: { current: number | null; previous: number | null };
  note?: string;
  inverse?: boolean; // for metrics where down is good (bounce, errors, latency)
}) {
  const delta = compareValue
    ? deltaPercent(compareValue.current, compareValue.previous)
    : null;
  const good = delta !== null && (inverse ? delta < 0 : delta > 0);
  return (
    <div className="rise rounded-xl border border-line bg-surface px-4 py-3" title={note}>
      <div className="text-xs font-medium text-ink-soft">{label}</div>
      <div className="tnum mt-1 font-display text-2xl font-bold tracking-tight">{value}</div>
      {delta !== null && (
        <div className={`tnum mt-0.5 text-xs font-semibold ${good ? "text-up" : "text-down"}`}>
          {delta > 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(1)} %
        </div>
      )}
    </div>
  );
}

export function RankedTable({
  rows,
  dimension,
  labelFor,
  onRowClick,
  valueFormatter = formatNumber,
}: {
  rows: QueryRow[] | undefined;
  dimension: string;
  labelFor?: (raw: string) => string;
  onRowClick?: (raw: string) => void;
  valueFormatter?: (value: number | null) => string;
}) {
  const { t } = useTranslation();
  if (!rows) return <SkeletonRows />;
  const sorted = [...rows].sort((a, b) => (b.value ?? 0) - (a.value ?? 0)).slice(0, 12);
  if (sorted.length === 0) {
    return <p className="py-6 text-center text-sm text-ink-soft">{t("web.empty")}</p>;
  }
  const max = sorted[0]?.value ?? 1;
  return (
    <ul className="space-y-1">
      {sorted.map((row) => {
        const raw = String(row[dimension] ?? "");
        const label = labelFor ? labelFor(raw) : raw || t("web.direct");
        const width = max ? Math.max(4, ((row.value ?? 0) / max) * 100) : 0;
        const inner = (
          <>
            <span
              className="rank-fill absolute inset-y-0 left-0 rounded-md"
              style={{ width: `${width}%` }}
              aria-hidden
            />
            <span className="relative truncate pr-3 text-sm">{label}</span>
            <span className="tnum relative ml-auto text-sm font-semibold">
              {valueFormatter(row.value)}
            </span>
          </>
        );
        return (
          <li key={raw || "—"}>
            {onRowClick ? (
              <button
                onClick={() => onRowClick(raw)}
                className="relative flex w-full items-center rounded-md px-2 py-1.5 text-left hover:outline hover:outline-1 hover:outline-line"
              >
                {inner}
              </button>
            ) : (
              <div className="relative flex items-center rounded-md px-2 py-1.5">{inner}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

export function SkeletonRows() {
  return (
    <div className="animate-pulse space-y-2 py-1">
      {Array.from({ length: 6 }).map((_, index) => (
        <div key={index} className="h-6 rounded-md bg-line/60" style={{ width: `${95 - index * 12}%` }} />
      ))}
    </div>
  );
}

export function Tabs<T extends string>({
  value,
  options,
  onChange,
  labelFor,
}: {
  value: T;
  options: readonly T[];
  onChange: (next: T) => void;
  labelFor: (option: T) => string;
}) {
  return (
    <div className="flex gap-1 text-xs">
      {options.map((option) => (
        <button
          key={option}
          onClick={() => onChange(option)}
          className={`rounded-md px-2 py-1 font-medium ${
            option === value ? "bg-flame-soft text-flame" : "text-ink-soft hover:text-ink"
          }`}
        >
          {labelFor(option)}
        </button>
      ))}
    </div>
  );
}

/** Contextual glossary (PRD #75 / #76). Renders a metric/dimension label with a
 *  discreet "i" that opens a plain-language definition (short + optional pitfall
 *  note + optional "learn more" link). Trilingual via i18n; the definitions are
 *  guaranteed complete for every registry term by the Python completeness gate.
 *
 *  Interaction is click (keyboard + mobile accessible); the popover closes on
 *  outside-click or Escape. When a term has no shipped definition it degrades to
 *  a bare label. */

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { docsUrl } from "../lib/docs";
import { hasGlossary, termKind, type TermKind } from "../lib/glossary";

export function TermLabel({ name, kind }: { name: string; kind?: TermKind }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const popId = useId();

  const resolvedKind = kind ?? termKind(name);
  const label = t(`${resolvedKind}.${name}`);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // No shipped definition → plain label (no dangling affordance).
  if (!hasGlossary(name)) return <>{label}</>;

  const short = t(`glossary.${name}.short`);
  const note = t(`glossary.${name}.note`, { defaultValue: "" });
  const docsSlug = t(`glossary.${name}.docsSlug`, { defaultValue: "" });

  return (
    <span ref={ref} className="relative inline-flex items-center gap-1 font-normal">
      {label}
      <button
        type="button"
        aria-label={t("glossaryUi.whatIs", { term: label })}
        aria-expanded={open}
        aria-controls={open ? popId : undefined}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-line text-[10px] font-semibold leading-none text-ink-soft hover:border-flame hover:text-flame focus:outline-none focus:ring-1 focus:ring-flame"
      >
        i
      </button>
      {open && (
        <span
          id={popId}
          role="tooltip"
          className="absolute left-0 top-6 z-50 w-64 rounded-md border border-line bg-surface p-3 text-left text-xs font-normal normal-case tracking-normal text-ink shadow-lg"
        >
          <span className="block font-semibold">{label}</span>
          <span className="mt-1 block text-ink-soft">{short}</span>
          {note && <span className="mt-2 block italic text-ink-soft">{note}</span>}
          {docsSlug && (
            <a
              href={docsUrl(docsSlug)}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block font-medium text-flame underline-offset-2 hover:underline"
            >
              {t("glossaryUi.learnMore")}
            </a>
          )}
        </span>
      )}
    </span>
  );
}

export default TermLabel;

/** Contextual glossary (PRD #75 / #76). Renders a metric/dimension label with a
 *  discreet "i" that discloses a plain-language definition (short + optional
 *  pitfall note + optional "learn more" link). Trilingual via i18n; the
 *  definitions are guaranteed complete for every registry term by the Python
 *  completeness gate.
 *
 *  Interaction is click (keyboard + mobile accessible); the disclosure closes on
 *  outside-click or Escape. When a term has no shipped definition it degrades to
 *  a bare label. */

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { docsUrl } from "../lib/docs";
import { hasGlossary, termKind, type TermKind } from "../lib/glossary";

/** The shipped definition body for a term — shared by the `<TermLabel>` popover
 *  and the central Glossary page so the two never drift. */
export function GlossaryDefinition({ name }: { name: string }) {
  const { t } = useTranslation();
  const note = t(`glossary.${name}.note`, { defaultValue: "" });
  const docsSlug = t(`glossary.${name}.docsSlug`, { defaultValue: "" });
  return (
    <>
      <p className="text-sm text-ink-soft">{t(`glossary.${name}.short`)}</p>
      {note && <p className="mt-1 text-xs italic text-ink-soft">{note}</p>}
      {docsSlug && (
        <a
          href={docsUrl(docsSlug)}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-block text-xs font-medium text-flame underline-offset-2 hover:underline"
        >
          {t("glossaryUi.learnMore")}
        </a>
      )}
    </>
  );
}

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
          className="absolute left-0 top-6 z-50 block w-64 rounded-md border border-line bg-surface p-3 text-left normal-case tracking-normal shadow-lg"
        >
          <span className="mb-1 block text-sm font-semibold text-ink">{label}</span>
          <GlossaryDefinition name={name} />
        </span>
      )}
    </span>
  );
}

export default TermLabel;

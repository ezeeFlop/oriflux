/** Contextual glossary (PRD #75 / #76). Renders a metric/dimension label with a
 *  discreet "i" that discloses a plain-language definition (short + optional
 *  pitfall note + optional "learn more" link). Trilingual via i18n; the
 *  definitions are guaranteed complete for every registry term by the Python
 *  completeness gate.
 *
 *  The popover is rendered in a portal on document.body (fixed-positioned under
 *  the button) so it escapes every card's stacking context / overflow — grid
 *  KPI tiles each create their own context, so an in-card z-index isn't enough.
 *  Click to toggle (keyboard + mobile accessible); closes on outside-click,
 *  Escape, or scroll. Degrades to a bare label when a term has no definition. */

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { docsUrl } from "../lib/docs";
import { hasGlossary, termKind, type TermKind } from "../lib/glossary";

const POPOVER_WIDTH = 256; // w-64

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
        <Link
          to={docsUrl(docsSlug)}
          className="mt-1 inline-block text-xs font-medium text-flame underline-offset-2 hover:underline"
        >
          {t("glossaryUi.learnMore")}
        </Link>
      )}
    </>
  );
}

export function TermLabel({ name, kind }: { name: string; kind?: TermKind }) {
  const { t } = useTranslation();
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);

  const resolvedKind = kind ?? termKind(name);
  const label = t(`${resolvedKind}.${name}`);

  useEffect(() => {
    if (!pos) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node;
      if (btnRef.current?.contains(target) || popRef.current?.contains(target)) return;
      setPos(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPos(null);
    };
    const close = () => setPos(null);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", close, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("resize", close);
    };
  }, [pos]);

  // No shipped definition → plain label (no dangling affordance).
  if (!hasGlossary(name)) return <>{label}</>;

  const toggle = () => {
    if (pos) {
      setPos(null);
      return;
    }
    const r = btnRef.current?.getBoundingClientRect();
    if (r) {
      setPos({
        top: r.bottom + 4,
        left: Math.max(8, Math.min(r.left, window.innerWidth - POPOVER_WIDTH - 8)),
      });
    }
  };

  return (
    <span className="inline-flex items-center gap-1 font-normal">
      {label}
      <button
        ref={btnRef}
        type="button"
        aria-label={t("glossaryUi.whatIs", { term: label })}
        aria-expanded={pos !== null}
        onClick={toggle}
        className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-line text-[10px] font-semibold leading-none text-ink-soft hover:border-flame hover:text-flame focus:outline-none focus:ring-1 focus:ring-flame"
      >
        i
      </button>
      {pos !== null &&
        createPortal(
          <div
            ref={popRef}
            role="group"
            aria-label={label}
            style={{ position: "fixed", top: pos.top, left: pos.left, width: POPOVER_WIDTH }}
            className="z-[100] rounded-md border border-line bg-surface p-3 text-left normal-case tracking-normal shadow-lg"
          >
            <span className="mb-1 block text-sm font-semibold text-ink">{label}</span>
            <GlossaryDefinition name={name} />
          </div>,
          document.body,
        )}
    </span>
  );
}

export default TermLabel;

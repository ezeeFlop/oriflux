/** Per-screen help (PRD #75 / #77). A discreet "?" next to a screen's subtitle
 *  opens a drawer explaining, in plain language: what the screen is for, how to
 *  read it, and the next useful action — plus a docs link. Trilingual via i18n;
 *  extends the #70 pedagogy subtitles. Reuses the #76 design system/tone.
 *
 *  Wired once through <ScreenSubtitle>, so every screen carrying a subtitle gets
 *  help automatically. Closes on backdrop click, the ✕, or Escape. Degrades to
 *  nothing when a screen has no help entry. */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import i18n from "../i18n";
import { docsUrl } from "../lib/docs";

const BLOCKS = ["purpose", "howToRead", "nextAction"] as const;

export function ScreenHelpButton({ id }: { id: string }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // No help entry for this screen → no affordance.
  if (!i18n.exists(`screenHelp.${id}.purpose`)) return null;

  const docsSlug = t(`screenHelp.${id}.docsSlug`, { defaultValue: "" });

  return (
    <>
      <button
        type="button"
        aria-label={t("screenHelpUi.open")}
        aria-haspopup="dialog"
        onClick={() => setOpen(true)}
        className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-line text-xs font-semibold text-ink-soft hover:border-flame hover:text-flame focus:outline-none focus:ring-1 focus:ring-flame"
      >
        ?
      </button>
      {open && (
        <div className="fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-ink/30"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label={t("screenHelpUi.title")}
            className="absolute right-0 top-0 flex h-full w-full max-w-sm flex-col border-l border-line bg-surface shadow-xl"
          >
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <h2 className="text-sm font-semibold text-ink">{t("screenHelpUi.title")}</h2>
              <button
                type="button"
                aria-label={t("screenHelpUi.close")}
                onClick={() => setOpen(false)}
                className="rounded-md px-2 py-1 text-sm text-ink-soft hover:text-flame focus:outline-none focus:ring-1 focus:ring-flame"
              >
                ✕
              </button>
            </div>
            <div className="overflow-y-auto px-4 py-4 text-sm">
              {BLOCKS.map((block) => (
                <section key={block} className="mb-4 last:mb-3">
                  <h3 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
                    {t(`screenHelpUi.${block}`)}
                  </h3>
                  <p className="mt-1 text-ink">{t(`screenHelp.${id}.${block}`)}</p>
                </section>
              ))}
              {docsSlug && (
                <Link
                  to={docsUrl(docsSlug)}
                  onClick={() => setOpen(false)}
                  className="inline-block font-medium text-flame underline-offset-2 hover:underline"
                >
                  {t("screenHelpUi.learnMore")}
                </Link>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default ScreenHelpButton;

import { useTranslation } from "react-i18next";
import type { SectionKey } from "../lib/sections";

/** Placeholder for IA sections whose slice has not shipped yet (Phase 3.5).
 *  Each upcoming slice replaces one of these with the real screen. */
export default function ComingSoon({ section }: { section: SectionKey }) {
  const { t } = useTranslation();
  return (
    <div className="rise mx-auto mt-16 max-w-md rounded-lg border border-dashed border-line bg-surface p-8 text-center">
      <p className="font-display text-lg font-bold">{t(`nav.${section}`)}</p>
      <p className="mt-2 text-sm font-semibold text-flame">{t("coming.title")}</p>
      <p className="mt-1 text-sm text-ink-soft">{t("coming.body")}</p>
    </div>
  );
}

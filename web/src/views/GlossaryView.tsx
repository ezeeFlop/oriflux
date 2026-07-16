/** Central Glossary page (PRD #75 / #76): the single reference listing every
 *  metric and dimension with its plain-language definition, pitfalls and a link
 *  to the docs. Terms are derived from the i18n glossary namespace (kept in sync
 *  with the query registry by the Python completeness gate). */

import { useTranslation } from "react-i18next";

import { GlossaryDefinition } from "../components/TermLabel";
import { dimensionTerms, metricTerms, type TermKind } from "../lib/glossary";

function TermRow({ name, kind }: { name: string; kind: TermKind }) {
  const { t } = useTranslation();
  return (
    <div className="border-b border-line py-3 last:border-0">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-semibold text-ink">{t(`${kind}.${name}`)}</h3>
        <code className="shrink-0 text-[11px] text-ink-soft/70">{name}</code>
      </div>
      <div className="mt-1">
        <GlossaryDefinition name={name} />
      </div>
    </div>
  );
}

export default function GlossaryView() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-2xl px-4 py-6">
      <h1 className="text-xl font-semibold text-ink">{t("glossaryUi.title")}</h1>
      <p className="mt-1 text-sm text-ink-soft">{t("glossaryUi.subtitle")}</p>

      <section className="mt-6">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
          {t("glossaryUi.metrics")}
        </h2>
        <div className="mt-2">
          {metricTerms.map((name) => (
            <TermRow key={name} name={name} kind="metric" />
          ))}
        </div>
      </section>

      <section className="mt-8">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-ink-soft">
          {t("glossaryUi.dimensions")}
        </h2>
        <div className="mt-2">
          {dimensionTerms.map((name) => (
            <TermRow key={name} name={name} kind="dimension" />
          ))}
        </div>
      </section>
    </div>
  );
}

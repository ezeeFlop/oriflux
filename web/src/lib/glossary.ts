/** Glossary term lists, derived from the i18n bundle so they can never drift
 *  from the definitions that ship. The Python completeness gate
 *  (api/tests/unit/test_glossary_completeness.py) guarantees `glossary.*` covers
 *  exactly the query registry (metrics + dimensions), so iterating the glossary
 *  namespace here is equivalent to iterating the registry — without an API call.
 *
 *  A term is a *metric* when it also has a `metric.<name>` label; otherwise it is
 *  a *dimension*. (`glossary.*` holds only term entries — UI strings live under
 *  `glossaryUi.*`.) */

import en from "../i18n/en.json";

export type TermKind = "metric" | "dimension";

const GLOSSARY = en.glossary as Record<string, unknown>;
const METRIC = en.metric as Record<string, unknown>;

export const metricTerms: string[] = Object.keys(GLOSSARY).filter((k) => k in METRIC);
export const dimensionTerms: string[] = Object.keys(GLOSSARY).filter((k) => !(k in METRIC));

export function termKind(name: string): TermKind {
  return name in METRIC ? "metric" : "dimension";
}

/** True when a term has a shipped glossary definition (so `<TermLabel>` should
 *  show the "i" affordance rather than a bare label). */
export function hasGlossary(name: string): boolean {
  return name in GLOSSARY;
}

/** In-app documentation content (PRD #75 / #78). The 6 public guides in
 *  `docs/public/**.md` are the single source — rendered here in the dashboard
 *  AND on the Astro landing. Bundled at build time via import.meta.glob so the
 *  docs work offline and switch locale instantly.
 *
 *  Layout: `docs/public/<slug>.md` (FR, canonical), `docs/public/en/<slug>.md`,
 *  `docs/public/es/<slug>.md`. README is not a guide. */

const RAW = import.meta.glob("../../../docs/public/**/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

export type DocLang = "fr" | "en" | "es";

/** Display order of the guides (the rest, if any, follow alphabetically). */
const ORDER = [
  "getting-started",
  "oriflux-js",
  "python-sdk",
  "api-mcp",
  "self-hosting",
  "privacy",
];

const byLangSlug: Record<string, string> = {};
const frSlugs = new Set<string>();

for (const [path, content] of Object.entries(RAW)) {
  const m = path.match(/docs\/public\/(?:(en|es)\/)?([^/]+)\.md$/);
  if (!m) continue;
  const [, langDir, slug] = m;
  if (slug.toLowerCase() === "readme") continue;
  const lang: DocLang = (langDir as DocLang) ?? "fr";
  byLangSlug[`${lang}/${slug}`] = content;
  if (lang === "fr") frSlugs.add(slug);
}

export const docSlugs: string[] = [...frSlugs].sort(
  (a, b) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99) || a.localeCompare(b),
);

/** Raw markdown for a slug in the requested locale, falling back es→en→fr. */
export function getDoc(slug: string, lang: DocLang): string | undefined {
  return (
    byLangSlug[`${lang}/${slug}`] ??
    byLangSlug[`en/${slug}`] ??
    byLangSlug[`fr/${slug}`]
  );
}

/** The first "# Heading" of a doc, used as its title in the index/header. */
export function docTitle(slug: string, lang: DocLang): string {
  const md = getDoc(slug, lang);
  const h1 = md?.match(/^\s*#\s+(.+?)\s*$/m);
  return h1 ? h1[1] : slug;
}

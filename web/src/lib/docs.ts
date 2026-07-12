import i18n from "../i18n";

/** Public site (landing + docs, slice #72/#73). The final domain is a build
 *  variable — everything is built against sponge-theory.dev until then. */
const PUBLIC_SITE =
  (import.meta.env.VITE_PUBLIC_SITE as string | undefined) ??
  "https://oriflux.sponge-theory.dev";

/** Locale-aware public docs URL: FR is the root, EN under /en (the docs
 *  have no ES locale — Spanish UI users get the EN guides). */
export function docsUrl(slug: string): string {
  const prefix = i18n.language === "fr" ? "" : "/en";
  return `${PUBLIC_SITE}${prefix}/docs/${slug}`;
}

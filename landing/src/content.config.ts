import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

// Docs markdown lives OUTSIDE landing/ — the single source of truth is
// ../docs/public (FR) and ../docs/public/en (EN). We never copy them in;
// the glob loader reads them at build time. README.md is excluded — it is
// the maintainer index, not a published guide.
const docsFr = defineCollection({
  loader: glob({ pattern: ["*.md", "!README.md"], base: "../docs/public" }),
  schema: z.object({}).passthrough(),
});

const docsEn = defineCollection({
  loader: glob({ pattern: ["*.md", "!README.md"], base: "../docs/public/en" }),
  schema: z.object({}).passthrough(),
});

export const collections = { docsFr, docsEn };

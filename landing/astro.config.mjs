import { defineConfig } from "astro/config";

// Static-output landing + docs. FR is the root ("/"), EN under "/en/".
// We deliberately do NOT use Astro's i18n routing config — the two locales
// are plain page trees (src/pages/index.astro, src/pages/en/index.astro) so
// the URL shape is fully explicit and the dashboard's deep-links stay stable.
export default defineConfig({
  output: "static",
  build: {
    format: "directory",
  },
  trailingSlash: "always",
  markdown: {
    // Light code theme to match the oriflamme light system (docs.css styles the
    // <pre> shell — surface bg, line border; Shiki colors the tokens on top).
    shikiConfig: {
      theme: "github-light",
      wrap: false,
    },
  },
});

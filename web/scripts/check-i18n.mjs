// i18n parity guard (issue #22): every locale must expose the exact same
// key set — a missing key silently falls back and ships mixed languages.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const locales = ["fr", "en", "es"];

const flatten = (obj, prefix = "") =>
  Object.entries(obj).flatMap(([key, value]) =>
    typeof value === "object" && value !== null
      ? flatten(value, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  );

const keysByLocale = new Map(
  locales.map((locale) => [
    locale,
    new Set(flatten(JSON.parse(readFileSync(join(here, `../src/i18n/${locale}.json`), "utf8")))),
  ]),
);

const reference = keysByLocale.get("fr");
let failed = false;
for (const [locale, keys] of keysByLocale) {
  const missing = [...reference].filter((k) => !keys.has(k));
  const extra = [...keys].filter((k) => !reference.has(k));
  if (missing.length || extra.length) {
    failed = true;
    console.error(`✗ ${locale}: missing=[${missing}] extra=[${extra}]`);
  }
}
if (failed) process.exit(1);
console.log(`✓ i18n parity: ${locales.join("/")} share ${reference.size} keys`);

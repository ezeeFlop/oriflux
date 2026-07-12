#!/usr/bin/env node
// Strict fr/en parity — same shape (keys, array lengths), content is free.
// Does not compare the translations themselves: a different string between
// fr.json and en.json is normal, a missing key or item is not. Build gate.
// (walk() logic reused from the Spongram landing.)
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const frPath = join(here, "..", "src", "content", "fr.json");
const enPath = join(here, "..", "src", "content", "en.json");

const fr = JSON.parse(readFileSync(frPath, "utf8"));
const en = JSON.parse(readFileSync(enPath, "utf8"));

const errors = [];

function kindOf(v) {
  if (Array.isArray(v)) return "array";
  if (v === null) return "null";
  return typeof v;
}

function walk(a, b, path) {
  const ka = kindOf(a);
  const kb = kindOf(b);
  if (ka !== kb) {
    errors.push(`${path}: type mismatch (fr=${ka}, en=${kb})`);
    return;
  }
  if (ka === "array") {
    if (a.length !== b.length) {
      errors.push(`${path}: length mismatch (fr=${a.length}, en=${b.length})`);
      return;
    }
    a.forEach((item, i) => walk(item, b[i], `${path}[${i}]`));
  } else if (ka === "object") {
    const keysA = Object.keys(a).sort();
    const keysB = Object.keys(b).sort();
    const onlyInFr = keysA.filter((k) => !keysB.includes(k));
    const onlyInEn = keysB.filter((k) => !keysA.includes(k));
    if (onlyInFr.length) errors.push(`${path}: keys only in fr.json — ${onlyInFr.join(", ")}`);
    if (onlyInEn.length) errors.push(`${path}: keys only in en.json — ${onlyInEn.join(", ")}`);
    for (const k of keysA) {
      if (keysB.includes(k)) walk(a[k], b[k], path ? `${path}.${k}` : k);
    }
  }
  // leaf strings/numbers: content is allowed to differ, no check.
}

walk(fr, en, "");

if (errors.length) {
  console.error(`✗ i18n parity — ${errors.length} fr/en mismatch(es):`);
  for (const e of errors) console.error(`  - ${e}`);
  process.exit(1);
}

console.log("✓ i18n parity — fr.json and en.json have exactly the same shape.");

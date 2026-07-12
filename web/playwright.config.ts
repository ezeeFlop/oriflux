/** E2E smoke against the local dev compose stack (#66 quality item).
 *  Deliberately NOT part of `npm test` — run with `npm run test:e2e` when
 *  the deploy/ stack is up; the global setup skips everything otherwise. */

import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  timeout: 45_000,
  retries: 1,
  use: {
    baseURL: process.env.ORIFLUX_E2E_WEB_URL ?? "http://localhost:8103",
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
  },
  reporter: [["list"]],
});

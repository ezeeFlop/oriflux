/** Dashboard e2e smoke (#66): drives the real dev stack end to end — login
 *  gate, portfolio, overview cockpit, web analytics, API analytics — through
 *  the same nginx + FastAPI + ClickHouse path production uses. */

import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const here = dirname(fileURLToPath(import.meta.url));
const sessionPath = join(here, ".auth", "session.json");
const session = existsSync(sessionPath)
  ? (JSON.parse(readFileSync(sessionPath, "utf-8")) as {
      org: string;
      projectId: string | null;
      token: string;
    })
  : null;

test.skip(session === null, "deploy/ compose stack is not running");

test.beforeEach(async ({ page }) => {
  await page.goto("/login");
  await page.evaluate(
    ([token, org]) => {
      localStorage.setItem("oriflux.token", token);
      localStorage.setItem("oriflux.org", org);
      localStorage.setItem("oriflux.lang", "fr");
    },
    [session!.token, session!.org],
  );
});

test("unauthenticated visitors land on the login screen", async ({ page }) => {
  await page.evaluate(() => localStorage.clear());
  await page.goto("/");
  await expect(page.getByText("Le plan de contrôle analytics de Sponge Theory")).toBeVisible();
});

test("portfolio home renders project tiles and the live section", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("h1", { hasText: "Portefeuille" })).toBeVisible();
  await expect(page.getByText("Pages actives (30 min)")).toBeVisible();
});

test("the project overview is the /p/:id index and shows the KPI band", async ({ page }) => {
  await page.goto(`/p/${session!.projectId}?period=30d`);
  await expect(page).toHaveURL(new RegExp(`/p/${session!.projectId}/overview`));
  await expect(page.getByText("Tendance web + API")).toBeVisible();
  await expect(page.getByText("Requêtes API").first()).toBeVisible();
});

test("web analytics renders the stat row and geography through the registry", async ({ page }) => {
  await page.goto(`/p/${session!.projectId}/web?period=30d`);
  await expect(page.getByText("Visiteurs").first()).toBeVisible();
  await expect(page.locator("h2", { hasText: "Géographie" }).first()).toBeVisible();
  await expect(page.locator("h2", { hasText: "Visibilité IA" })).toBeVisible();
});

test("api analytics renders endpoints and caller geography", async ({ page }) => {
  await page.goto(`/p/${session!.projectId}/api?period=30d`);
  await expect(page.getByText("Points d'accès")).toBeVisible();
  await expect(page.getByText("Géographie des appelants")).toBeVisible();
});

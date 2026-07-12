import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import type { QueryRequest } from "../lib/api";
import { renderApp } from "./render";
import { server } from "./server";

/** Pedagogy slice (#70): one-line subtitles everywhere; empty screens hand
 *  the user the action (real snippet, SDK install, inline create, docs). */

const zeroQueries = () =>
  http.post("/api/v1/query", async ({ request }) => {
    const body = (await request.json()) as QueryRequest;
    return HttpResponse.json({
      metric: body.metric,
      results: [{ value: 0, bucket: "2026-07-10T00:00:00Z" }],
      compare_results: body.compare_to ? [{ value: 0 }] : null,
      sql: "SELECT 1",
    });
  });

beforeEach(() => {
  server.use(
    http.get("/api/v1/orgs/:orgId/alert-rules", () => HttpResponse.json([])),
    http.get("/api/v1/projects/:projectId/sources", () =>
      HttpResponse.json([
        { id: "s-web", project_id: "p1", type: "web", name: "site" },
        { id: "s-api", project_id: "p1", type: "api", name: "backend" },
      ]),
    ),
    http.post("/api/v1/sources/:sourceId/keys", () =>
      HttpResponse.json({
        id: "k1",
        key: "ofx_ing_TESTKEY",
        key_prefix: "ofx_ing_TES",
        scope: "ingest",
        name: "site",
      }),
    ),
  );
});

describe("screen subtitles", () => {
  it("shows a one-line purpose under each screen title", async () => {
    renderApp("/p/p1/web");
    expect(
      await screen.findByText(
        "L'audience de votre site — visiteurs, pages, sources et géographie, sans cookies.",
      ),
    ).toBeInTheDocument();
  });

  it("covers the portfolio home too", async () => {
    renderApp("/");
    expect(
      await screen.findByText(
        "Tous vos produits d'un coup d'œil — visiteurs live, tendances et alertes récentes.",
      ),
    ).toBeInTheDocument();
  });
});

describe("web empty state", () => {
  it("offers the snippet flow when the project emitted no web events", async () => {
    server.use(zeroQueries());
    renderApp("/p/p1/web");
    expect(await screen.findByText("Aucun événement web sur la période")).toBeInTheDocument();
    expect(screen.getByText(/oriflux\.js/)).toBeInTheDocument();
  });

  it("issues a real key inline and fills the snippet with it", async () => {
    server.use(zeroQueries());
    const user = userEvent.setup();
    renderApp("/p/p1/web");
    await user.click(await screen.findByRole("button", { name: "Générer la clé et le snippet" }));
    await waitFor(() =>
      expect(screen.getByText(/data-key="ofx_ing_TESTKEY"/)).toBeInTheDocument(),
    );
    expect(
      screen.getByText("La clé ne sera plus jamais affichée — copiez le snippet maintenant."),
    ).toBeInTheDocument();
  });

  it("stays away when the project has web data", async () => {
    renderApp("/p/p1/web");
    await screen.findAllByText("Visiteurs");
    expect(screen.queryByText("Aucun événement web sur la période")).not.toBeInTheDocument();
  });
});

describe("api empty state", () => {
  it("shows the SDK install instructions when the API emitted nothing", async () => {
    server.use(zeroQueries());
    renderApp("/p/p1/api");
    expect(await screen.findByText("Aucun trafic API sur la période")).toBeInTheDocument();
    expect(screen.getByText(/pip install oriflux-sdk/)).toBeInTheDocument();
  });
});

describe("create-inline empty states with docs links", () => {
  it("alerts: empty rules point at the inline form and the docs", async () => {
    renderApp("/p/p1/alerts");
    expect(await screen.findByText(/Aucune règle d'alerte/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Créer la règle" })).toBeInTheDocument();
    const docsLinks = screen.getAllByRole("link", { name: "Consulter la documentation →" });
    expect(docsLinks[0].getAttribute("href")).toContain("/docs/getting-started");
  });

  it("goals: empty list keeps the creation form and links the docs", async () => {
    renderApp("/p/p1/goals");
    expect(await screen.findByText(/Aucun objectif/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ajouter" })).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Consulter la documentation →" }).length,
    ).toBeGreaterThan(0);
  });

  it("annotations: empty list keeps the creation form and links the docs", async () => {
    renderApp("/p/p1/annotations");
    expect(await screen.findByText(/Aucune annotation/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Annoter" })).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Consulter la documentation →" }).length,
    ).toBeGreaterThan(0);
  });
});

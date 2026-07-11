import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import { renderApp } from "./render";
import { server } from "./server";

let hasOrg: boolean;
let firstEventSeen: boolean;

beforeEach(() => {
  hasOrg = false;
  firstEventSeen = false;
  server.use(
    http.get("/api/v1/me", () =>
      HttpResponse.json({
        id: "user-1",
        email: "new@sponge-theory.io",
        name: "New",
        orgs: hasOrg ? [{ org_id: "org-9", role: "owner" }] : [],
      }),
    ),
    http.post("/api/v1/orgs", async ({ request }) => {
      const body = (await request.json()) as { slug: string; name: string };
      hasOrg = true;
      return HttpResponse.json({ id: "org-9", ...body }, { status: 201 });
    }),
    http.post("/api/v1/orgs/:orgId/projects", async ({ request }) => {
      const body = (await request.json()) as { slug: string; name: string };
      return HttpResponse.json({ id: "p-9", org_id: "org-9", ...body }, { status: 201 });
    }),
    http.post("/api/v1/projects/:projectId/sources", async ({ request }) => {
      const body = (await request.json()) as { type: string; name: string };
      return HttpResponse.json(
        { id: "s-9", project_id: "p-9", ...body },
        { status: 201 },
      );
    }),
    http.post("/api/v1/sources/:sourceId/keys", () =>
      HttpResponse.json(
        {
          id: "k-9",
          key: "ofx_ing_WELCOME_PLAINTEXT",
          key_prefix: "ofx_ing_wlc",
          scope: "ingest",
          name: "site",
        },
        { status: 201 },
      ),
    ),
    http.post("/api/v1/query", () =>
      HttpResponse.json({
        metric: "pageviews",
        results: [{ value: firstEventSeen ? 3 : 0 }],
        compare_results: null,
        sql: "SELECT 1",
      }),
    ),
  );
});

describe("self-serve onboarding (issue #62)", () => {
  it("sends an org-less user to the welcome flow instead of an empty shell", async () => {
    renderApp("/");
    expect(await screen.findByText("Bienvenue sur Oriflux")).toBeInTheDocument();
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
  });

  it("walks org → project → source → key/snippet → first event", async () => {
    const user = userEvent.setup();
    renderApp("/welcome");
    await user.type(await screen.findByLabelText("Nom de l'organisation"), "Ma Boîte");
    await user.type(screen.getByLabelText("Slug de l'organisation"), "ma-boite");
    await user.click(screen.getByRole("button", { name: "Créer l'organisation" }));

    await user.type(await screen.findByLabelText("Nom du projet"), "Mon App");
    await user.type(screen.getByLabelText("Slug du projet"), "mon-app");
    await user.click(screen.getByRole("button", { name: "Créer le projet" }));

    await user.type(await screen.findByLabelText("Nom de la source"), "monapp.io");
    await user.click(screen.getByRole("button", { name: "Ajouter la source" }));

    // the key appears once, with the paste-ready snippet
    expect(await screen.findByText("ofx_ing_WELCOME_PLAINTEXT")).toBeInTheDocument();
    expect(screen.getByText(/data-key="ofx_ing_WELCOME_PLAINTEXT"/)).toBeInTheDocument();
    expect(await screen.findByText(/En attente du premier événement/)).toBeInTheDocument();

    // the probe flips: the flow confirms the integration works
    firstEventSeen = true;
    expect(
      await screen.findByText("Premier événement reçu — l'intégration fonctionne !", undefined, {
        timeout: 8000,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ouvrir le portefeuille" })).toBeInTheDocument();
  }, 20_000);

  it("sends an invited member straight to the portfolio", async () => {
    hasOrg = true;
    renderApp("/welcome");
    expect(await screen.findByRole("heading", { name: "Portefeuille" })).toBeInTheDocument();
  });
});

import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { renderApp } from "./render";
import { server } from "./server";

describe("public shared dashboard", () => {
  it("renders the safe subset with the shared widgets (no auth, no private nav)", async () => {
    server.use(
      http.post("/public/:token/query", async ({ request }) => {
        const body = (await request.json()) as { dimensions?: string[] };
        const dimension = body.dimensions?.[0];
        const results =
          dimension === "page"
            ? [{ value: 120, page: "/docs" }]
            : dimension === "country"
              ? [{ value: 80, country: "FR" }]
              : [{ value: 456 }];
        return HttpResponse.json({ results });
      }),
    );
    renderApp("/public/ofx_pub_token", { authenticated: false });
    expect(await screen.findByText("Tableau de bord public")).toBeInTheDocument();
    expect(await screen.findByText("456")).toBeInTheDocument();
    expect(await screen.findByText("/docs")).toBeInTheDocument();
    // the choropleth from the web view is reused on the public page
    expect(await screen.findByText(/France — 80/)).toBeInTheDocument();
    // no private shell around a public page
    expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Portefeuille" })).not.toBeInTheDocument();
  });

  it("shows a clean translated state on a revoked link", async () => {
    server.use(
      http.post("/public/:token/query", () =>
        HttpResponse.json({ detail: "revoked" }, { status: 404 }),
      ),
    );
    renderApp("/public/ofx_pub_revoked", { authenticated: false });
    expect(
      await screen.findByText("Ce lien de partage est invalide ou a été révoqué."),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Ce lien de partage a été révoqué ou n'existe pas."),
    ).toBeInTheDocument();
  });
});

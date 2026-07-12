import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import type { Connector } from "../lib/api";
import { renderApp } from "./render";
import { server } from "./server";

let connectors: Connector[];
let zeusService: string | null;

beforeEach(() => {
  connectors = [];
  zeusService = null;
  server.use(
    http.get("/api/v1/projects/:projectId/connectors", () => HttpResponse.json(connectors)),
    http.post("/api/v1/projects/:projectId/connectors", async ({ request }) => {
      const body = (await request.json()) as { provider: Connector["provider"] };
      const connector: Connector = {
        id: `c-${connectors.length + 1}`,
        provider: body.provider,
        webhook_path: `/api/v1/connectors/c-${connectors.length + 1}/webhook`,
      };
      connectors = [...connectors, connector];
      return HttpResponse.json(connector, { status: 201 });
    }),
    http.delete("/api/v1/connectors/:connectorId", ({ params }) => {
      connectors = connectors.filter((c) => c.id !== params.connectorId);
      return new HttpResponse(null, { status: 204 });
    }),
    http.get("/api/v1/projects/:projectId/zeus", () =>
      HttpResponse.json({ zeus_service: zeusService }),
    ),
    http.patch("/api/v1/projects/:projectId/zeus", async ({ request }) => {
      const body = (await request.json()) as { zeus_service: string | null };
      zeusService = body.zeus_service;
      return HttpResponse.json({ zeus_service: zeusService });
    }),
    http.get("/api/v1/projects/:projectId/infra", () =>
      zeusService === null
        ? HttpResponse.json({ available: false })
        : HttpResponse.json({
            available: true,
            service: zeusService,
            cpu_percent: 12.5,
            memory_mb: 384,
            containers: 3,
          }),
    ),
  );
});

describe("project settings — connectors (#57)", () => {
  it("creates a connector, shows its webhook path, deletes it", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/settings");
    expect(await screen.findByText("Aucun connecteur.")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Fournisseur"), "lemonsqueezy");
    await user.type(
      screen.getByLabelText("Secret de signature du webhook"),
      "whsec_supersecret",
    );
    await user.click(screen.getByRole("button", { name: "Ajouter le connecteur" }));

    expect(await screen.findByText("lemonsqueezy")).toBeInTheDocument();
    expect(screen.getByText("/api/v1/connectors/c-1/webhook")).toBeInTheDocument();
    // the secret input is cleared and the secret never displayed
    expect(screen.queryByText("whsec_supersecret")).not.toBeInTheDocument();

    const row = screen.getByText("lemonsqueezy").closest("li") as HTMLElement;
    await user.click(within(row).getByRole("button", { name: "Supprimer le connecteur" }));
    expect(await screen.findByText("Aucun connecteur.")).toBeInTheDocument();
  });
});

describe("project settings — Zeus (#58)", () => {
  it("maps a Zeus service and shows the live infra snapshot", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/settings");
    expect(await screen.findByText("Aucun service associé.")).toBeInTheDocument();

    await user.type(await screen.findByLabelText("Service Zeus"), "spt-oriflux_api");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(await screen.findByText("12.5 % CPU")).toBeInTheDocument();
    expect(screen.getByText("384 MB RAM")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Dissocier" }));
    expect(await screen.findByText("Aucun service associé.")).toBeInTheDocument();
  });
});

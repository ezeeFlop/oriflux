import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";
import type { AlertRule } from "../lib/api";
import { renderApp } from "./render";
import { server } from "./server";

let rules: AlertRule[];

beforeEach(() => {
  rules = [];
  server.use(
    http.get("/api/v1/orgs/:orgId/alert-rules", () => HttpResponse.json(rules)),
    http.post("/api/v1/orgs/:orgId/alert-rules", async ({ request }) => {
      const body = (await request.json()) as Omit<AlertRule, "id" | "enabled" | "slack_webhook_url" | "email">;
      const rule: AlertRule = {
        id: `r-${rules.length + 1}`,
        enabled: true,
        slack_webhook_url: null,
        email: null,
        ...body,
      };
      rules = [...rules, rule];
      return HttpResponse.json(rule, { status: 201 });
    }),
    http.patch("/api/v1/alert-rules/:ruleId", async ({ params, request }) => {
      const patch = (await request.json()) as Partial<AlertRule>;
      rules = rules.map((r) => (r.id === params.ruleId ? { ...r, ...patch } : r));
      return HttpResponse.json(rules.find((r) => r.id === params.ruleId));
    }),
    http.delete("/api/v1/alert-rules/:ruleId", ({ params }) => {
      rules = rules.filter((r) => r.id !== params.ruleId);
      return new HttpResponse(null, { status: 204 });
    }),
    http.get("/api/v1/orgs/:orgId/alert-events", () =>
      HttpResponse.json([
        {
          id: "ev-1",
          rule_id: "r-9",
          rule_name: "Latence p95",
          project_id: "p1",
          metric: "api_latency_p95",
          value: 900,
          fired_at: "2026-07-11T09:00:00Z",
          resolved_at: "2026-07-11T09:20:00Z",
        },
      ]),
    ),
  );
});

describe("alerts screen", () => {
  it("creates a rule scoped to the current project", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/alerts");
    await user.type(await screen.findByLabelText("Nom de la règle"), "5xx haut");
    await user.selectOptions(screen.getByLabelText("Métrique"), "api_error_rate_5xx");
    await user.click(screen.getByRole("button", { name: "Créer la règle" }));
    expect(await screen.findByText("5xx haut")).toBeInTheDocument();
    expect(rules[0].filters).toEqual([{ dimension: "project_id", op: "eq", value: "p1" }]);
    const row = screen.getByText("5xx haut").closest("li") as HTMLElement;
    expect(within(row).getByText("Active")).toBeInTheDocument();
  });

  it("pauses, resumes and deletes a rule", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/alerts");
    await user.type(await screen.findByLabelText("Nom de la règle"), "seuil visiteurs");
    await user.click(screen.getByRole("button", { name: "Créer la règle" }));
    const row = () => screen.getByText("seuil visiteurs").closest("li") as HTMLElement;

    await user.click(within(row()).getByRole("button", { name: "Mettre en pause" }));
    expect(await within(row()).findByText("En pause")).toBeInTheDocument();

    await user.click(within(row()).getByRole("button", { name: "Réactiver" }));
    expect(await within(row()).findByText("Active")).toBeInTheDocument();

    await user.click(within(row()).getByRole("button", { name: "Supprimer la règle" }));
    expect(await screen.findByText("Aucune règle d'alerte pour ce projet.")).toBeInTheDocument();
  });

  it("shows the event feed with rule name and resolved state", async () => {
    renderApp("/p/p1/alerts");
    expect(await screen.findByText("Latence p95", { selector: "strong" })).toBeInTheDocument();
    expect(await screen.findByText(/Résolue/)).toBeInTheDocument();
  });
});

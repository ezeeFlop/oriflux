import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import * as redirect from "../lib/redirect";
import { renderApp } from "./render";
import { server } from "./server";

const ENABLED = {
  enabled: true,
  plan_slug: "free",
  has_customer: true,
  plans: [
    { slug: "free", name: "Free", monthly_events: 100000, subscribable: false },
    { slug: "pro", name: "Pro", monthly_events: 1000000, subscribable: true },
  ],
};

describe("billing section (issue #63)", () => {
  it("stays invisible on a keyless instance", async () => {
    renderApp("/settings/org");
    expect(await screen.findByText("Plan & usage")).toBeInTheDocument();
    expect(screen.queryByText("Abonnement")).not.toBeInTheDocument();
  });

  it("offers the subscribable upgrades and redirects to checkout", async () => {
    server.use(
      http.get("/api/v1/orgs/:orgId/billing", () => HttpResponse.json(ENABLED)),
      http.post("/api/v1/orgs/:orgId/billing/checkout", () =>
        HttpResponse.json({ url: "https://checkout.stripe.test/pro" }),
      ),
    );
    const assign = vi.spyOn(redirect, "redirectTo").mockImplementation(() => {});
    const user = userEvent.setup();
    renderApp("/settings/org");
    await user.click(await screen.findByRole("button", { name: "Passer en Pro" }));
    expect(assign).toHaveBeenCalledWith("https://checkout.stripe.test/pro");
  });

  it("opens the customer portal for an existing subscriber", async () => {
    server.use(
      http.get("/api/v1/orgs/:orgId/billing", () => HttpResponse.json(ENABLED)),
      http.post("/api/v1/orgs/:orgId/billing/portal", () =>
        HttpResponse.json({ url: "https://portal.stripe.test/cus_1" }),
      ),
    );
    const assign = vi.spyOn(redirect, "redirectTo").mockImplementation(() => {});
    const user = userEvent.setup();
    renderApp("/settings/org");
    await user.click(
      await screen.findByRole("button", { name: "Gérer l'abonnement (factures, annulation)" }),
    );
    expect(assign).toHaveBeenCalledWith("https://portal.stripe.test/cus_1");
  });
});

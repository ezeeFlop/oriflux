import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderApp } from "./render";

/** The mobile nav duplicates the sidebar links (hidden by CSS only, which
 *  jsdom ignores) — assertions scope to the desktop sidebar. */
const sidebar = () => within(screen.getByRole("complementary"));

describe("shell", () => {
  it("redirects unauthenticated visitors to the login page", async () => {
    renderApp("/", { authenticated: false });
    expect(
      await screen.findByText("Le plan de contrôle analytics de Sponge Theory"),
    ).toBeInTheDocument();
  });

  it("renders the portfolio home with the org's projects", async () => {
    renderApp("/");
    expect(await sidebar().findByRole("link", { name: "AudiGEO" })).toBeInTheDocument();
    expect(await sidebar().findByRole("link", { name: "NeoRAG" })).toBeInTheDocument();
  });

  it("shows the full project sidebar (target IA) inside a project", async () => {
    renderApp("/p/p1/web");
    for (const name of [
      "Vue d'ensemble",
      "Web",
      "API",
      "Live",
      "Funnels & rétention",
      "Objectifs",
      "Alertes",
      "Annotations",
      "Réglages projet",
    ]) {
      expect(await sidebar().findByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("renders a translated placeholder on not-yet-built sections", async () => {
    renderApp("/p/p1/overview");
    expect(await screen.findByText("Bientôt dans la refonte")).toBeInTheDocument();
  });

  it("switches theme from the account menu and persists it", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Compte" }));
    await user.click(await screen.findByRole("button", { name: "Thème" }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("oriflux.theme")).toBe("dark");
    await user.click(screen.getByRole("button", { name: "Thème" }));
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(localStorage.getItem("oriflux.theme")).toBe("light");
  });

  it("switches language from the account menu and persists it", async () => {
    const user = userEvent.setup();
    renderApp("/");
    await user.click(await screen.findByRole("button", { name: "Compte" }));
    await user.click(await screen.findByRole("button", { name: "English" }));
    expect(await sidebar().findByRole("link", { name: "Portfolio" })).toBeInTheDocument();
    expect(localStorage.getItem("oriflux.lang")).toBe("en");
  });
});

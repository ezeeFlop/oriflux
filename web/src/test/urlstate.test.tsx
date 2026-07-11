import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { currentLocation, renderApp } from "./render";

describe("period & compare in the URL", () => {
  it("defaults to 7d with compare off", async () => {
    renderApp("/p/p1/web");
    const button = await screen.findByRole("button", { name: "7 jours" });
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("checkbox", { name: "Comparer" })).not.toBeChecked();
  });

  it("restores period and compare from the URL", async () => {
    renderApp("/p/p1/web?period=90d&compare=1");
    const button = await screen.findByRole("button", { name: "90 jours" });
    expect(button).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("checkbox", { name: "Comparer" })).toBeChecked();
  });

  it("falls back to 7d on an invalid period value", async () => {
    renderApp("/p/p1/web?period=nope");
    const button = await screen.findByRole("button", { name: "7 jours" });
    expect(button).toHaveAttribute("aria-pressed", "true");
  });

  it("writes the picked period to the URL", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/web");
    await user.click(await screen.findByRole("button", { name: "30 jours" }));
    expect(currentLocation()).toContain("period=30d");
  });

  it("writes the compare toggle to the URL", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/web");
    await user.click(await screen.findByRole("checkbox", { name: "Comparer" }));
    expect(currentLocation()).toContain("compare=1");
  });

  it("keeps the period when entering a project from a home card", async () => {
    const user = userEvent.setup();
    renderApp("/?period=30d");
    const main = within(await screen.findByRole("main"));
    await user.click(await main.findByRole("heading", { name: "AudiGEO" }));
    expect(currentLocation()).toContain("/p/p1/web");
    expect(currentLocation()).toContain("period=30d");
  });

  it("keeps the period while navigating between views", async () => {
    const user = userEvent.setup();
    renderApp("/p/p1/web?period=90d");
    const aside = within(await screen.findByRole("complementary"));
    await user.click(await aside.findByRole("link", { name: "API" }));
    expect(currentLocation()).toContain("/p/p1/api");
    expect(currentLocation()).toContain("period=90d");
  });
});

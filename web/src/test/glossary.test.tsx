import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { TermLabel } from "../components/TermLabel";
import { dimensionTerms, metricTerms } from "../lib/glossary";
import "../i18n"; // initialise the global i18n instance (defaults to FR in tests)
import { renderApp } from "./render";

/** Glossary slice (PRD #75 / #76): contextual `<TermLabel>` popovers + the
 *  central Glossary page. Definitions ship trilingual; tests run in FR. */

describe("TermLabel", () => {
  it("shows the label and reveals the definition only after clicking the 'i'", async () => {
    render(<TermLabel name="visitors" kind="metric" />);
    // label always visible
    expect(screen.getByText("Visiteurs")).toBeInTheDocument();
    // definition hidden until opened
    expect(screen.queryByText(/personnes distinctes/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Qu'est-ce que/ }));
    expect(screen.getByText(/personnes distinctes/i)).toBeInTheDocument();
    // the visitors pitfall note (cross-day dedup) is surfaced
    expect(screen.getByText(/minuit/i)).toBeInTheDocument();
  });

  it("degrades to a bare label for a term with no glossary entry", () => {
    render(<TermLabel name="project_id" kind="dimension" />);
    expect(screen.getByText("Projet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Qu'est-ce que/ })).not.toBeInTheDocument();
  });
});

describe("term lists derived from the i18n bundle", () => {
  it("classifies metrics and dimensions and covers the shipped glossary", () => {
    expect(metricTerms).toContain("sessions");
    expect(metricTerms).toContain("api_latency_p95");
    expect(dimensionTerms).toContain("traffic_class");
    expect(dimensionTerms).toContain("country");
    // project_id is exempt from the glossary → absent from the rendered lists
    expect(dimensionTerms).not.toContain("project_id");
    expect(metricTerms.length + dimensionTerms.length).toBe(38);
  });
});

describe("central Glossary page", () => {
  it("renders the glossary with metric and dimension sections", async () => {
    renderApp("/glossary");
    expect(await screen.findByRole("heading", { name: "Glossaire", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("Métriques")).toBeInTheDocument();
    expect(screen.getByText("Dimensions")).toBeInTheDocument();
    // a real definition renders (bounce_rate short, FR)
    expect(screen.getByText(/une seule page avant de repartir/i)).toBeInTheDocument();
  });
});

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import DocsView from "../views/DocsView";
import "../i18n";

function renderDocs(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/docs" element={<DocsView />} />
        <Route path="/docs/:slug" element={<DocsView />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("in-app docs (#78)", () => {
  it("lists the guides at /docs", () => {
    renderDocs("/docs");
    expect(screen.getByRole("heading", { name: "Documentation", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("getting-started")).toBeInTheDocument();
    expect(screen.getByText("self-hosting")).toBeInTheDocument();
  });
  it("renders a guide's markdown at /docs/:slug", () => {
    renderDocs("/docs/self-hosting");
    expect(screen.getByRole("heading", { name: "Auto-hébergement" })).toBeInTheDocument();
  });
});

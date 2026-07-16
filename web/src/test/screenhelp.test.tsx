import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { ScreenHelpButton } from "../components/ScreenHelp";
import "../i18n"; // initialise global i18n (defaults to FR in tests)

/** Per-screen help slice (PRD #75 / #77): a "?" next to each subtitle opens a
 *  drawer with the three explanatory blocks. Tests run in FR. */

describe("ScreenHelpButton (#77)", () => {
  it("opens a drawer with the three help blocks for a screen", async () => {
    render(<MemoryRouter><ScreenHelpButton id="web" /></MemoryRouter>);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Aide de l'écran/ }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("À quoi sert cet écran")).toBeInTheDocument();
    expect(screen.getByText("Comment le lire")).toBeInTheDocument();
    expect(screen.getByText("Prochaine action utile")).toBeInTheDocument();
    // real web-screen purpose content renders
    expect(screen.getByText(/audience de votre site/i)).toBeInTheDocument();
  });

  it("renders nothing for a screen with no help entry", () => {
    const { container } = render(<MemoryRouter><ScreenHelpButton id="does-not-exist" /></MemoryRouter>);
    expect(container).toBeEmptyDOMElement();
  });
});

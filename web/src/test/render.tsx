import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { AppRoutes } from "../App";
import { auth } from "../lib/api";

/** Mirrors the router location so tests can assert on path + query string. */
function LocationProbe() {
  const location = useLocation();
  return (
    <output data-testid="location">
      {location.pathname}
      {location.search}
    </output>
  );
}

export function renderApp(route = "/", { authenticated = true } = {}) {
  if (authenticated) {
    auth.token = "test-token";
    auth.orgId = "org-1";
  }
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <AppRoutes />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export function currentLocation(): string {
  const probe = document.querySelector('[data-testid="location"]');
  return probe?.textContent ?? "";
}

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./i18n";
import "./styles.css";
import Shell from "./components/Shell";
import { auth } from "./lib/api";
import { DashboardProvider } from "./lib/state";
import ApiView from "./views/ApiView";
import HomeView from "./views/HomeView";
import Login from "./views/Login";
import WebView from "./views/WebView";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
  },
});

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!auth.token) return <Navigate to="/login" replace />;
  return children;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            element={
              <RequireAuth>
                <DashboardProvider>
                  <Shell />
                </DashboardProvider>
              </RequireAuth>
            }
          >
            <Route path="/" element={<HomeView />} />
            <Route path="/p/:projectId/web" element={<WebView />} />
            <Route path="/p/:projectId/api" element={<ApiView />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);

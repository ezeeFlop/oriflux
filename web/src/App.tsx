import { Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import Shell from "./components/Shell";
import { auth } from "./lib/api";
import { PROJECT_SECTIONS, type SectionKey } from "./lib/sections";
import { DashboardProvider } from "./lib/state";
import ApiView from "./views/ApiView";
import AlertsView from "./views/AlertsView";
import ComingSoon from "./views/ComingSoon";
import GoalsView from "./views/GoalsView";
import HomeView from "./views/HomeView";
import ProductView from "./views/ProductView";
import Login from "./views/Login";
import OrgSettingsView from "./views/OrgSettingsView";
import PublicView from "./views/PublicView";
import WebView from "./views/WebView";

/** Sections whose slice already shipped; everything else is a placeholder. */
const SECTION_VIEWS: Partial<Record<SectionKey, JSX.Element>> = {
  web: <WebView />,
  api: <ApiView />,
  product: <ProductView />,
  goals: <GoalsView />,
  alerts: <AlertsView />,
};

function RequireAuth({ children }: { children: JSX.Element }) {
  if (!auth.token) return <Navigate to="/login" replace />;
  return children;
}

/** /p/:id lands on the web view until the project overview slice ships. */
function ProjectIndexRedirect() {
  const { projectId } = useParams();
  const { search } = useLocation();
  return <Navigate to={`/p/${projectId}/web${search}`} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/public/:token" element={<PublicView />} />
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
        <Route path="/settings/org" element={<OrgSettingsView />} />
        <Route path="/p/:projectId" element={<ProjectIndexRedirect />} />
        {PROJECT_SECTIONS.map(({ key, path }) => (
          <Route
            key={key}
            path={`/p/:projectId/${path}`}
            element={SECTION_VIEWS[key] ?? <ComingSoon section={key} />}
          />
        ))}
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

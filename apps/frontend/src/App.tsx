import {
  Activity,
  BookOpenText,
  ChartNoAxesColumnIncreasing,
  CircleHelp,
  Network,
  Settings2,
} from "lucide-react";
import {
  BrowserRouter,
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import ResearchPage from "./pages/ResearchPage";
import EvaluationsPage from "./pages/EvaluationsPage";
import ArchitecturePage from "./pages/ArchitecturePage";
import SystemStatusPage from "./pages/SystemStatusPage";
import SettingsPage from "./pages/SettingsPage";
import { WorkbenchProvider } from "./state/WorkbenchContext";
import "./App.css";

const navigation = [
  { label: "Research", to: "/research", icon: BookOpenText },
  {
    label: "Evaluations",
    to: "/evaluations",
    icon: ChartNoAxesColumnIncreasing,
  },
  { label: "Architecture", to: "/architecture", icon: Network },
  { label: "System status", to: "/status", icon: Activity },
];

function ApplicationFrame() {
  const location = useLocation();
  const currentPage = navigation.find((item) => item.to === location.pathname);

  return (
    <div className="application-shell">
      <aside className="sidebar">
        <NavLink className="brand" to="/research" aria-label="PolicyLens home">
          <span className="brand-mark" aria-hidden="true">
            P
          </span>
          <span className="brand-name">PolicyLens</span>
        </NavLink>
        <p className="sidebar-caption">RESEARCH DESK</p>
        <nav aria-label="Primary navigation" className="primary-navigation">
          {navigation.map(({ label, to, icon: Icon }) => (
            <NavLink
              className={({ isActive }) =>
                `navigation-link${isActive ? " is-active" : ""}`
              }
              key={to}
              to={to}
            >
              <Icon aria-hidden="true" size={18} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="local-status">
            <span className="status-pip" aria-hidden="true" />
            <span>Local workspace</span>
          </div>
          <NavLink className="settings-link" to="/settings">
            <Settings2 aria-hidden="true" size={17} />
            <span>Model settings</span>
          </NavLink>
        </div>
      </aside>

      <div className="workspace-column">
        <header className="topbar">
          <div className="breadcrumb" aria-live="polite">
            <span>POLICYLENS</span>
            <span className="breadcrumb-divider" aria-hidden="true">
              /
            </span>
            <span>{currentPage?.label ?? "Model settings"}</span>
          </div>
          <Link
            className="icon-button help-link"
            to="/architecture"
            aria-label="Open architecture guide"
            title="Architecture guide"
          >
            <CircleHelp aria-hidden="true" size={18} />
          </Link>
        </header>
        <main className="main-content" id="main-content" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Navigate replace to="/research" />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/evaluations" element={<EvaluationsPage />} />
            <Route path="/architecture" element={<ArchitecturePage />} />
            <Route path="/status" element={<SystemStatusPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <WorkbenchProvider>
        <ApplicationFrame />
      </WorkbenchProvider>
    </BrowserRouter>
  );
}

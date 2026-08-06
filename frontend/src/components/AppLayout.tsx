import { NavLink, Outlet } from "react-router";
import { useEffect, useState } from "react";
import { getHealth } from "../lib/api";

type ApiConnectionStatus = "checking" | "connected" | "unavailable";

const navigationItems = [
  { label: "Dashboard", path: "/" },
  { label: "Jobs", path: "/jobs" },
  { label: "Applications", path: "/applications" },
  { label: "Profile", path: "/profile" },
];


function AppLayout() {
  const [apiStatus, setApiStatus] =
    useState<ApiConnectionStatus>("checking");

  useEffect(() => {
    const controller = new AbortController();

    async function checkApiConnection() {
      try {
        await getHealth(controller.signal);
        setApiStatus("connected");
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }

        setApiStatus("unavailable");
      }
    }

    void checkApiConnection();

    return () => {
      controller.abort();
    };
  }, []);

  const apiStatusLabel = {
    checking: "Checking API",
    connected: "API connected",
    unavailable: "API unavailable",
  }[apiStatus];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
        <img
        src="public/logoJM.png"
        alt="JobMatch"
        className="brand-mark"
        />
          <div>
            <strong>JobMatch</strong>
          </div>
        </div>

        <nav className="navigation" aria-label="Main navigation">
          {navigationItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) =>
                isActive ? "navigation-link active" : "navigation-link"
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span>Local-first AI</span>
          <small>Powered by FastAPI and Ollama</small>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <div>
            <span className="eyebrow">Job search workspace</span>
          </div>

      <div className={`api-status api-status-${apiStatus}`}>
        <span className="status-indicator" />
        {apiStatusLabel}
      </div>
        </header>

        <main className="page-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default AppLayout;
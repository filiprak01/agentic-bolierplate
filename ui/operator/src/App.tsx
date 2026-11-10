import { Menu, ShieldCheck, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { operatorProjectConfig } from "./operatorConfig";
import { operatorRoutes, type OperatorRouteId } from "./navigation";
import { POInboxPanel } from "./POInboxPanel";
import { OperatorStatusPanel } from "./OperatorStatusPanel";
import { CodexLimitsPanel } from "./CodexLimitsPanel";
import { AgentMessagesPanel } from "./AgentMessagesPanel";

export function App() {
  const [activeRouteId, setActiveRouteId] = useState<OperatorRouteId>("po-inbox");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const activeRoute = useMemo(
    () => operatorRoutes.find((route) => route.id === activeRouteId) ?? operatorRoutes[0],
    [activeRouteId]
  );
  const ActiveIcon = activeRoute.icon;

  useEffect(() => {
    if (!drawerOpen) {
      return;
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setDrawerOpen(false);
      }
    }

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [drawerOpen]);

  function activateRoute(routeId: OperatorRouteId) {
    setActiveRouteId(routeId);
    setDrawerOpen(false);
  }

  return (
    <main className={`operator-shell ${drawerOpen ? "drawer-open" : ""}`}>
      <header className="operator-header">
        <button
          className="hamburger-button"
          type="button"
          aria-label="Open navigation"
          aria-controls="operator-navigation-drawer"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen(true)}
        >
          <Menu size={21} aria-hidden="true" />
        </button>

        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            A
          </div>
          <div>
            <p className="eyebrow">Local Operator</p>
            <h1>Agentic Console</h1>
          </div>
        </div>

        <div className="active-section-chip" aria-label="Active section">
          <ActiveIcon size={17} aria-hidden="true" />
          <span>{activeRoute.label}</span>
        </div>

        <div className="project-chip" title="Configured Jira project key">
          {operatorProjectConfig.jiraProjectKey}
        </div>
      </header>

      {drawerOpen ? (
        <>
          <button
            className="drawer-backdrop"
            type="button"
            aria-label="Close navigation"
            onClick={() => setDrawerOpen(false)}
          />

          <aside id="operator-navigation-drawer" className="navigation-drawer" aria-label="Operator navigation">
            <div className="drawer-header">
              <div>
                <p className="eyebrow">Navigation</p>
                <h2>Operator Areas</h2>
              </div>
              <button className="icon-button" type="button" onClick={() => setDrawerOpen(false)} title="Close navigation">
                <X size={18} aria-hidden="true" />
              </button>
            </div>

            <nav className="nav-list">
              {operatorRoutes.map((route) => {
                const Icon = route.icon;
                const isActive = route.id === activeRouteId;
                return (
                  <button
                    type="button"
                    key={route.id}
                    className={`nav-link ${isActive ? "selected" : ""}`}
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => activateRoute(route.id)}
                  >
                    <Icon size={18} aria-hidden="true" />
                    <span className="nav-copy">
                      <strong>{route.label}</strong>
                      <small>{route.description}</small>
                    </span>
                    {route.stateLabel ? <span className="nav-state">{route.stateLabel}</span> : null}
                  </button>
                );
              })}
            </nav>

            <div className="drawer-footer">
              <span className="row-title">Project</span>
              <span>{operatorProjectConfig.projectName}</span>
            </div>
          </aside>
        </>
      ) : null}

      <section className="content">
        <header className="topbar">
          <div>
            <p className="eyebrow">Active Project</p>
            <h2>{operatorProjectConfig.projectName}</h2>
          </div>
          <div className="section-title">
            <ActiveIcon size={22} aria-hidden="true" />
            <span>{activeRoute.label}</span>
          </div>
        </header>

        <section className="status-band" aria-label="Local-only data boundary">
          <ShieldCheck size={20} aria-hidden="true" />
          <div>
            <strong>Local-only shell</strong>
            <p>
              Reads platform durable data through the configured local API.
              Target project runtime folders are outside the UI data boundary.
            </p>
          </div>
        </section>

        <section className="section-workspace" aria-label={activeRoute.label}>
          <ActiveSection routeId={activeRouteId} />
        </section>
      </section>
    </main>
  );
}

function ActiveSection({ routeId }: { routeId: OperatorRouteId }) {
  if (routeId === "po-inbox") {
    return <POInboxPanel />;
  }
  if (routeId === "agent-status") {
    return <OperatorStatusPanel view="agent-status" />;
  }
  if (routeId === "codex-limits") {
    return <CodexLimitsPanel />;
  }
  if (routeId === "logs") {
    return <OperatorStatusPanel view="logs" />;
  }
  if (routeId === "agent-messages") {
    return <AgentMessagesPanel />;
  }

  const route = operatorRoutes.find((item) => item.id === routeId) ?? operatorRoutes[0];
  const Icon = route.icon;

  return (
    <section className="placeholder-panel" id={route.id}>
      <div className="section-heading">
        <div>
          <p className="eyebrow">Planned Section</p>
          <h3>{route.label}</h3>
        </div>
        <div className="route-icon" aria-hidden="true">
          <Icon size={22} />
        </div>
      </div>
      <p className="muted">{route.description}</p>
    </section>
  );
}

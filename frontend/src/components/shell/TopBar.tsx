import { useEffect, useState, type ReactNode } from "react";
import { RouteLink } from "../../app/RouteLink";
import type { Route } from "../../app/useRoute";
import { MISSION_LABEL, MISSION_TONE, type Tone } from "../../scenario/format";
import { useScenario } from "../../scenario/hooks";
import type { Connection } from "../../scenario/store";
import { Led } from "./Tone";

const CONNECTION: Record<Connection, { label: string; tone: Tone }> = {
  online: { label: "Online", tone: "ready" },
  connecting: { label: "Connecting", tone: "active" },
  offline: { label: "Backend offline", tone: "alert" },
};

function Stat({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="c-stat">
      <span className="c-label">{label}</span>
      <span className="c-stat-value">{children}</span>
    </div>
  );
}

function WallClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return (
    <time dateTime={now.toISOString()}>
      {now.toLocaleTimeString([], { hour12: false })}
    </time>
  );
}

const VIEWS: { route: Route; label: string }[] = [
  { route: "map", label: "Map" },
  { route: "launcher", label: "Launcher" },
];

export function TopBar({ route }: { route: Route }) {
  const { snapshot, connection } = useScenario();
  const link = CONNECTION[connection];

  return (
    <header className="c-top">
      <div className="c-brand">
        <span>SKUNKLABS</span>
      </div>

      <nav className="c-tabs" aria-label="Views">
        {VIEWS.map((view) => (
          <RouteLink
            key={view.route}
            to={view.route}
            className="c-tab"
            aria-current={route === view.route ? "page" : undefined}
          >
            {view.label}
          </RouteLink>
        ))}
      </nav>

      <div className="c-top-status">
        <Stat label={snapshot?.site.id ?? "Site"}>
          {snapshot
            ? snapshot.site.location_source === "DEVICE"
              ? "Your location"
              : "Default location"
            : "-"}
        </Stat>
        <Stat label="Mission">
          {snapshot ? (
            <>
              <Led tone={MISSION_TONE[snapshot.state]} />
              {MISSION_LABEL[snapshot.state]}
            </>
          ) : (
            "-"
          )}
        </Stat>
        <Stat label="Link">
          <Led tone={link.tone} />
          {link.label}
        </Stat>
        <Stat label="Mode">
          Simulation{snapshot ? ` · ×${snapshot.time_scale}` : ""}
        </Stat>
        <Stat label="Local">
          <WallClock />
        </Stat>
      </div>
    </header>
  );
}

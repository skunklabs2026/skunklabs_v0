import { useState } from "react";
import { ErrorBoundary } from "../common/ErrorBoundary";
import { EventLog } from "./EventLog";
import { StatusPanel } from "./StatusPanel";
import type {
  InterceptorState,
  InterceptSolution,
  MissionEvent,
  MissionStatus,
  SystemStatus,
  Target,
} from "../../types";

interface Props {
  system: SystemStatus | null;
  mission: MissionStatus | null;
  primary: Target | null;
  events: MissionEvent[];
  connected: boolean;
  intercept: InterceptSolution | null;
  interceptor: InterceptorState | null;
  /** Narrow viewport: show one section at a time behind tabs. */
  compact: boolean;
  onReset: () => void;
  onChangeSource: () => void;
}

type Tab = "status" | "events";

/**
 * The console's right-hand column: readouts, event log, controls.
 *
 * On a wide screen both sections are visible at once, which is what an
 * operator at a desk wants. On a phone that column would be a metre of
 * scrolling below the video, so the two sections become tabs and the video
 * stays in view.
 */
export function SidePanel({
  system,
  mission,
  primary,
  events,
  connected,
  intercept,
  interceptor,
  compact,
  onReset,
  onChangeSource,
}: Props) {
  const [tab, setTab] = useState<Tab>("status");

  // Unread count is only meaningful when the log is hidden behind a tab.
  const showStatus = !compact || tab === "status";
  const showEvents = !compact || tab === "events";

  return (
    <aside className="panel">
      {compact && (
        <div className="panel-tabs" role="tablist" aria-label="Console sections">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "status"}
            className={`panel-tab${tab === "status" ? " is-active" : ""}`}
            onClick={() => setTab("status")}
          >
            Status
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "events"}
            className={`panel-tab${tab === "events" ? " is-active" : ""}`}
            onClick={() => setTab("events")}
          >
            Events
            {events.length > 0 && (
              <span className="tab-count">{events.length}</span>
            )}
          </button>
        </div>
      )}

      {showStatus && (
        <ErrorBoundary label="Status">
          <StatusPanel
            system={system}
            mission={mission}
            primary={primary}
            connected={connected}
            intercept={intercept}
            interceptor={interceptor}
          />
        </ErrorBoundary>
      )}

      {showEvents && (
        <ErrorBoundary label="Event log">
          <EventLog events={events} />
        </ErrorBoundary>
      )}

      <div className="controls">
        <button type="button" className="ghost-button" onClick={onReset}>
          Reset Mission
        </button>
        <button type="button" className="ghost-button" onClick={onChangeSource}>
          Change Source
        </button>
      </div>
    </aside>
  );
}

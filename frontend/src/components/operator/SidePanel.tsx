import { useState } from "react";
import { ErrorBoundary } from "../common/ErrorBoundary";
import { CanisterPanel } from "./CanisterPanel";
import { DetailsPanel } from "./DetailsPanel";
import { EventLog } from "./EventLog";
import { ReadinessPanel } from "./ReadinessPanel";
import { TargetPanel } from "./TargetPanel";
import type {
  CanisterStatus,
  EngagementReadiness,
  LauncherStatus,
  MissionEvent,
  MissionState,
  SystemStatus,
  Target,
} from "../../types";

interface Props {
  system: SystemStatus | null;
  canister: CanisterStatus | null;
  readiness: EngagementReadiness | null;
  launcher: LauncherStatus | null;
  primary: Target | null;
  state: MissionState;
  events: MissionEvent[];
  connected: boolean;
  /** Narrow viewport: show one section at a time behind tabs. */
  compact: boolean;
  onReset: () => void;
  onChangeSource: () => void;
}

type Tab = "status" | "events";

/**
 * The console's right-hand column, in strict priority order:
 *
 *   TARGET      →  who the canister is acting on
 *   READINESS   →  whether it could engage, and what is blocking it
 *   CANISTER    →  whether the machine itself is healthy
 *   DETAILS     →  engineering information, collapsed
 *
 * On a wide screen everything is visible at once, which is what an operator
 * at a desk wants. On a phone that column would be a metre of scrolling below
 * the video, so status and events become tabs and the sensor view stays in
 * frame.
 */
export function SidePanel({
  system,
  canister,
  readiness,
  launcher,
  primary,
  state,
  events,
  connected,
  compact,
  onReset,
  onChangeSource,
}: Props) {
  const [tab, setTab] = useState<Tab>("status");

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
        <>
          <ErrorBoundary label="Target">
            <TargetPanel primary={primary} state={state} />
          </ErrorBoundary>
          <ErrorBoundary label="Readiness">
            <ReadinessPanel readiness={readiness} launcher={launcher} />
          </ErrorBoundary>
          <ErrorBoundary label="Canister">
            <CanisterPanel canister={canister} connected={connected} />
          </ErrorBoundary>
          <ErrorBoundary label="Details">
            <DetailsPanel primary={primary} system={system} />
          </ErrorBoundary>
        </>
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
          Canister Setup
        </button>
      </div>
    </aside>
  );
}

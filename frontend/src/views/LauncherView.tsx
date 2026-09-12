import { useState } from "react";
import { RouteLink } from "../app/RouteLink";
import { CameraFeed } from "../components/camera/CameraFeed";
import { ErrorBoundary } from "../components/common/ErrorBoundary";
import type { ModelStatus } from "../components/launcher/LauncherModel";
import { LauncherScene } from "../components/launcher/LauncherScene";
import { AxisReadout } from "../components/panels/AxisReadout";
import { DecisionPanel } from "../components/panels/DecisionPanel";
import { EventLog } from "../components/panels/EventLog";
import { InterceptorList } from "../components/panels/InterceptorList";
import { Inventory } from "../components/panels/Inventory";
import { NodeTabs } from "../components/panels/NodeTabs";
import { ConnectionOverlay } from "../components/shell/ConnectionOverlay";
import { NodeStatePill } from "../components/shell/Tone";
import { ENGAGEMENT_LABEL, formatHeading, formatKm } from "../scenario/format";
import { useScenario } from "../scenario/hooks";
import { displayedNodeId, findEngagement, findNode } from "../scenario/select";

/**
 * /launcher - "What is this node doing, and what simulated response am I
 * authorizing?" Shows one node at a time - by default the one behind the
 * current decision. Default export: loaded lazily, with three.js.
 */
export default function LauncherView() {
  const state = useScenario();
  const { snapshot, connection } = state;
  const [model, setModel] = useState<ModelStatus>({
    kind: "loading",
    detail: "Loading launcher model…",
  });
  const nodeId = displayedNodeId(state);
  const node = snapshot && nodeId ? findNode(snapshot, nodeId) : null;
  const engagement =
    snapshot && node?.engagement_id
      ? findEngagement(snapshot, node.engagement_id)
      : null;
  const interceptors =
    snapshot && engagement
      ? snapshot.interceptors.filter((i) => i.engagement_id === engagement.id)
      : [];

  return (
    <div className="c-launcher-view">
      <aside className="c-launcher-left">
        <RouteLink to="map" className="c-btn c-btn-small c-back">
          ← Back to map
        </RouteLink>
        <NodeTabs />

        <header className="c-launcher-head">
          <span className="c-label">Defense node</span>
          <h1>{node?.id ?? "-"}</h1>
          <p>360° yaw stage · pitch stage · 6-canister pack</p>
          {node && <NodeStatePill state={node.state} large />}
        </header>

        {node && (
          <>
            <dl className="c-kv c-launcher-track">
              <dt>Response</dt>
              <dd>
                {engagement
                  ? `${engagement.id} · ${ENGAGEMENT_LABEL[engagement.status]}`
                  : "None"}
              </dd>
              {engagement && (
                <>
                  <dt>Threat</dt>
                  <dd>{engagement.track_id}</dd>
                  <dt>Bearing</dt>
                  <dd>{formatHeading(engagement.bearing_deg)}</dd>
                  <dt>Range</dt>
                  <dd>{formatKm(engagement.range_km)}</dd>
                </>
              )}
            </dl>
            <AxisReadout
              kind="yaw"
              current={node.current_yaw_deg}
              requested={node.target_yaw_deg}
            />
            <AxisReadout
              kind="pitch"
              current={node.current_pitch_deg}
              requested={node.target_pitch_deg}
            />
            <div className="c-launcher-facts">
              <dl className="c-kv">
                <dt>Interceptors available</dt>
                <dd>
                  <Inventory
                    count={node.inventory}
                    capacity={node.inventory_capacity}
                  />
                </dd>
              </dl>
              {interceptors.length > 0 && (
                <div className="c-subsection">
                  <InterceptorList interceptors={interceptors} />
                </div>
              )}
            </div>
          </>
        )}
      </aside>

      <div className="c-launcher-center">
        <section className="c-launcher-stage" aria-label="3D launcher">
          <ErrorBoundary label="3D view">
            <LauncherScene nodeId={node?.id ?? null} onModelStatus={setModel} />
          </ErrorBoundary>
          <div className="c-stage-hud c-stage-tl">
            <span className="c-chip">
              {model.kind === "cad" ? "CAD model" : "Placeholder model"}
            </span>
          </div>
          <div className="c-stage-hud c-stage-tr">
            <span className="c-chip">Visual orientation only · no actuation</span>
          </div>
          <div className="c-stage-hud c-stage-bl">
            <span className="c-stage-note">Drag to orbit · scroll to zoom</span>
          </div>
        </section>
        <CameraFeed nodeId={node?.id ?? null} />
        {!snapshot && <ConnectionOverlay connection={connection} />}
      </div>

      <aside className="c-side">
        <DecisionPanel />
        <EventLog />
      </aside>
    </div>
  );
}

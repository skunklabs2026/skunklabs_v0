import { MapOverlay } from "../components/map/MapOverlay";
import { TacticalMap } from "../components/map/TacticalMap";
import { DecisionPanel } from "../components/panels/DecisionPanel";
import { EventLog } from "../components/panels/EventLog";
import { NodeList } from "../components/panels/NodeList";
import { ScenarioPicker } from "../components/panels/ScenarioPicker";
import { SitePanel } from "../components/panels/SitePanel";
import { ThreatList } from "../components/panels/ThreatList";
import { ConnectionOverlay } from "../components/shell/ConnectionOverlay";
import { useScenario } from "../scenario/hooks";

/**
 * /map: "What is threatening the infrastructure I am defending, and how is the
 * system responding?"
 */
export function MapView() {
  const { snapshot, connection } = useScenario();
  const idle = !snapshot || snapshot.state === "IDLE";

  return (
    <div className="c-map-view">
      <section className="c-map-stage" aria-label="Defense map">
        <TacticalMap />
        <MapOverlay />
        {!snapshot && <ConnectionOverlay connection={connection} />}
      </section>
      <aside className="c-side">
        {idle ? (
          <>
            <SitePanel />
            <ScenarioPicker />
          </>
        ) : (
          <>
            <DecisionPanel />
            <ThreatList />
          </>
        )}
        <NodeList />
        <EventLog />
      </aside>
    </div>
  );
}

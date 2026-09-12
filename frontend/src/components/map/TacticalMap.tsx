import "leaflet/dist/leaflet.css";
import { useEffect, useRef } from "react";
import { navigate } from "../../app/useRoute";
import { useScenarioStore, useScenarioValue } from "../../scenario/hooks";
import { currentDecision } from "../../scenario/select";
import { createTacticalMap, ScenarioLayers } from "./scenarioLayers";

/**
 * The Leaflet map. React owns only its lifecycle; the layers read the store
 * directly on every snapshot (see scenarioLayers.ts). Clicking a node opens it
 * in the launcher view.
 */
export function TacticalMap() {
  const container = useRef<HTMLDivElement>(null);
  const store = useScenarioStore();
  // Built once the layout is known, rebuilt only if the site or a node moves -
  // which is what happens when the device location arrives.
  const anchor = useScenarioValue((state) => {
    const snapshot = state.snapshot;
    if (!snapshot) return null;
    const points = [snapshot.site, ...snapshot.nodes];
    return points.map((p) => `${p.latitude},${p.longitude}`).join("|");
  });

  useEffect(() => {
    const element = container.current;
    const snapshot = store.getState().snapshot;
    if (!element || !anchor || !snapshot) return;

    const map = createTacticalMap(element, snapshot.site);
    const layers = new ScenarioLayers(map, snapshot, (nodeId) => {
      store.selectNode(nodeId);
      navigate("launcher");
    });
    const render = () => {
      const latest = store.getState().snapshot;
      if (latest) layers.update(latest, currentDecision(latest)?.id ?? null);
    };
    render();

    const unsubscribe = store.subscribe(render);
    const resize = new ResizeObserver(() => map.invalidateSize());
    resize.observe(element);

    return () => {
      unsubscribe();
      resize.disconnect();
      map.remove();
    };
  }, [store, anchor]);

  return (
    <div ref={container} className="c-map" role="region" aria-label="Defense map" />
  );
}

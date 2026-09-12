import { lazy, Suspense, useEffect } from "react";
import { useDeviceLocation } from "./app/useDeviceLocation";
import { useRoute, type Route } from "./app/useRoute";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { MissionBar } from "./components/shell/MissionBar";
import { TopBar } from "./components/shell/TopBar";
import { ScenarioStoreProvider, useScenarioStore } from "./scenario/hooks";
import { scenarioStore } from "./scenario/instance";
import { MapView } from "./views/MapView";

// three.js is only needed by the launcher view; keep it out of the first load.
const loadLauncherView = () => import("./views/LauncherView");
const LauncherView = lazy(loadLauncherView);
const SensorLab = lazy(() => import("./screens/SensorLab"));

/**
 * The SkunkLabs operator interface: two views over one mission state.
 *
 *   /map       what threatens the protected site, and how the defense responds
 *   /launcher  what a node is doing, and what response is being authorized
 *
 * plus the legacy video console at /sensor-lab, deliberately unlinked.
 */
export default function App() {
  const route = useRoute();

  if (route === "sensor-lab") {
    return (
      <Suspense fallback={null}>
        <SensorLab />
      </Suspense>
    );
  }
  return (
    <ScenarioStoreProvider value={scenarioStore}>
      <Console route={route} />
    </ScenarioStoreProvider>
  );
}

function Console({ route }: { route: Exclude<Route, "sensor-lab"> }) {
  const store = useScenarioStore();

  // One live feed for the whole console, so switching views never drops it.
  useEffect(() => store.connect(), [store]);

  // Centre the protected site on this device.
  useDeviceLocation();

  // Fetch the 3D chunk in the background so opening the launcher is instant.
  useEffect(() => {
    const id = window.setTimeout(() => void loadLauncherView(), 800);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <div className="c-console">
      <TopBar route={route} />
      <main className="c-main">
        <ErrorBoundary
          key={route}
          label={route === "launcher" ? "Launcher view" : "Map view"}
        >
          {route === "launcher" ? (
            <Suspense
              fallback={<div className="c-overlay">Loading launcher view…</div>}
            >
              <LauncherView />
            </Suspense>
          ) : (
            <MapView />
          )}
        </ErrorBoundary>
      </main>
      <MissionBar />
    </div>
  );
}

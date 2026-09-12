import { useCallback, useState } from "react";
import { ErrorBoundary } from "../components/common/ErrorBoundary";
import { useTelemetry } from "../hooks/useTelemetry";
import { OperatorScreen } from "./OperatorScreen";
import { SetupScreen } from "./SetupScreen";

// The sensor lab's own stylesheets, loaded only when it is opened.
import "../styles/setup.css";
import "../styles/operator.css";
import "../styles/responsive.css";

/**
 * The original video / computer-vision console, kept as a sensor lab at
 * #/sensor-lab. It needs the backend started with
 * SKUNK_VIDEO_PIPELINE_ENABLED=true.
 *
 * Its detector and tracker are the intended future track source for the V0
 * launcher scenario (see backend/scenario/track_source.py).
 */
export default function SensorLab() {
  const { telemetry, events, connected, authorize, reset } = useTelemetry();
  const [started, setStarted] = useState(false);

  const begin = useCallback(() => {
    // Start from a clean slate, so the operator watches a fresh sequence
    // rather than whatever accumulated during setup.
    void reset();
    setStarted(true);
  }, [reset]);

  return (
    <ErrorBoundary label="Sensor lab">
      {started ? (
        <OperatorScreen
          telemetry={telemetry}
          events={events}
          connected={connected}
          onAuthorize={() => void authorize()}
          onReset={() => void reset()}
          onChangeSource={() => setStarted(false)}
        />
      ) : (
        <SetupScreen telemetry={telemetry} connected={connected} onBegin={begin} />
      )}
    </ErrorBoundary>
  );
}

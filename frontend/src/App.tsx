import { useCallback, useState } from "react";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { OperatorScreen } from "./screens/OperatorScreen";
import { SetupScreen } from "./screens/SetupScreen";
import { useTelemetry } from "./hooks/useTelemetry";

/**
 * Routes between the two screens.
 *
 * The app opens on Mission Setup: load footage, confirm the detector is
 * seeing it, then begin. Nothing runs on the console until the operator has
 * chosen and verified a source.
 *
 * Telemetry is subscribed here rather than per screen, so switching screens
 * never drops and re-opens the socket.
 */
export default function App() {
  const { telemetry, events, connected, authorize, reset } = useTelemetry();
  const [started, setStarted] = useState(false);

  const begin = useCallback(() => {
    // Start from a clean slate, so the operator watches a fresh sequence
    // rather than whatever accumulated during setup.
    void reset();
    setStarted(true);
  }, [reset]);

  return (
    <ErrorBoundary label="Console">
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

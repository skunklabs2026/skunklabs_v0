import { EngagementOverlay, TargetLabels, VideoOverlay } from "./VideoOverlay";
import { endpoints } from "../../api";
import type {
  InterceptorState,
  InterceptSolution,
  MissionState,
  SystemStatus,
  Target,
} from "../../types";

interface Props {
  system: SystemStatus | null;
  targets: Target[];
  state: MissionState;
  intercept: InterceptSolution | null;
  interceptor: InterceptorState | null;
  launching: boolean;
  hasTelemetry: boolean;
}

/**
 * The sensor view and everything drawn on top of it.
 *
 * The inner `.frame` is locked to the source aspect ratio so the image fills
 * it exactly and the overlays — which use normalised coordinates — land on
 * the pixels they describe. Any letterboxing happens outside that box.
 */
export function VideoStage({
  system,
  targets,
  state,
  intercept,
  interceptor,
  launching,
  hasTelemetry,
}: Props) {
  const sensorOnline = Boolean(system?.sensor_online);
  // Fall back to 16:9 until the first frame reports real dimensions, so the
  // layout does not jump on connect.
  const frameWidth = system?.frame_width || 16;
  const frameHeight = system?.frame_height || 9;

  return (
    <div className="viewport">
      <div
        className="frame"
        style={{ aspectRatio: `${frameWidth} / ${frameHeight}` }}
      >
        <img className="feed" src={endpoints.videoStream()} alt="Sensor feed" />

        <VideoOverlay targets={targets} state={state} />
        <EngagementOverlay
          intercept={intercept}
          interceptor={interceptor}
          state={state}
        />
        <TargetLabels targets={targets} state={state} />

        <span className="corner tl" />
        <span className="corner tr" />
        <span className="corner bl" />
        <span className="corner br" />

        {/* Sensor identity, not model identity. Which detector is running is
            engineering information and lives under DETAILS. */}
        <div className="feed-meta">
          {system
            ? `SENSOR 01 · ${system.frame_width}×${system.frame_height} · ${system.fps.toFixed(0)} fps · frame ${system.frame_index}`
            : "awaiting sensor"}
        </div>

        {launching && (
          <>
            <div className="launch-flash" />
            <div className="launch-label">Launch Command Issued · Simulated</div>
          </>
        )}

        {!sensorOnline && hasTelemetry && (
          <div className="viewport-offline">
            <div>Sensor Offline</div>
            <div style={{ color: "var(--text-faint)" }}>Attempting to recover</div>
          </div>
        )}
      </div>
    </div>
  );
}

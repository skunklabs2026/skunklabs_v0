import { Row } from "../common/Readout";
import type { DetectionStats, SystemStatus } from "../../types";

interface Props {
  system: SystemStatus | null;
  detection: DetectionStats | null;
  sourceName: string | null;
  live: boolean;
}

/**
 * Evidence that the pipeline is working on *this* footage.
 *
 * This is the answer to "does it actually track my video?" - frames flowing,
 * detections accumulating, tracks forming, and which classes are being seen.
 */
export function VerifyPanel({ system, detection, sourceName, live }: Props) {
  const classes = detection?.classes ?? [];

  return (
    <div className="verify">
      <Row label="Source" value={sourceName ?? "-"} muted={!sourceName} />
      <Row
        label="Frames"
        value={
          system
            ? `${detection?.frames_processed ?? 0} @ ${system.fps.toFixed(0)} fps`
            : "-"
        }
        muted={!system}
      />
      <Row
        label="Detections"
        value={`${detection?.detections_total ?? 0} / ${detection?.detections_last_frame ?? 0} now`}
        muted={!detection?.detections_total}
      />
      <Row
        label="Active tracks"
        value={String(detection?.active_tracks ?? 0)}
        muted={!detection?.active_tracks}
      />
      <Row
        label="Inference"
        value={detection?.latency_ms ? `${detection.latency_ms} ms` : "-"}
        muted={!detection?.latency_ms}
      />

      <div className="chips">
        {classes.map((entry) => (
          <span key={entry.name} className="chip">
            {entry.name} <b>{entry.count}</b>
          </span>
        ))}
        {live && classes.length === 0 && (
          <span className="note">
            Nothing detected yet - try the other detector, or lower the confidence
            threshold.
          </span>
        )}
      </div>
    </div>
  );
}

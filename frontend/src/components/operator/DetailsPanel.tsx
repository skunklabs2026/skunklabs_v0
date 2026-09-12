import { useState } from "react";
import { Row } from "../common/Readout";
import { PLATFORM_LABEL, TRACK_STABILITY_LABEL } from "../../format";
import type { SystemStatus, Target } from "../../types";

interface Props {
  primary: Target | null;
  system: SystemStatus | null;
}

/**
 * Engineering detail, collapsed by default.
 *
 * Everything here answers "how is it doing that", not "what is it doing".
 * An investor or a first-time operator should be able to follow the whole
 * mission without opening this; an engineer debugging a clip needs all of it.
 *
 * >>> WHAT IS NOT HERE, AND WHY <<<
 * "Time to impact" and an inferred range used to sit on the main panel. They
 * are gone. Both are derived from an image-plane extrapolation with no camera
 * calibration behind it, so presenting them as seconds and metres was false
 * precision - they read as measurements and are not. What survives is the
 * TRACK PROJECTION: direction, stability, horizon and confidence, all stated
 * as sensor-frame quantities.
 */
export function DetailsPanel({ primary, system }: Props) {
  const [open, setOpen] = useState(false);

  const projection = primary?.projection ?? null;
  const features = primary?.platform_features ?? null;
  const speed = primary?.speed ?? null;

  return (
    <div className="card details">
      <button
        type="button"
        className="details-toggle"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        <span>Details</span>
        <span className="details-chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
      </button>

      {open && (
        <div className="details-body">
          <div className="details-group">
            <div className="details-title">
              Track projection <span className="tag">Sensor frame</span>
            </div>
            <div className="readout">
              <Row
                label="Direction"
                value={projection?.valid ? projection.direction_label : "-"}
                muted={!projection?.valid}
                title="Direction of travel within the camera frame - not a compass bearing."
              />
              <Row
                label="Stability"
                value={
                  TRACK_STABILITY_LABEL[projection?.stability ?? "UNAVAILABLE"]
                }
                muted={!projection?.valid}
              />
              <Row
                label="Horizon"
                value={
                  projection?.valid ? `${projection.horizon.toFixed(1)} s` : "-"
                }
                muted={!projection?.valid}
                title="Scaled by airframe class - a fixed-wing holds its course further."
              />
              <Row
                label="Confidence"
                value={
                  projection?.valid
                    ? `${Math.round(projection.confidence * 100)}%`
                    : "-"
                }
                muted={!projection?.valid}
                title="Quality of the motion fit, not a probability that anything will happen."
              />
            </div>
          </div>

          <div className="details-group">
            <div className="details-title">
              Airframe <span className="tag">Inferred</span>
            </div>
            <div className="readout">
              <Row
                label="Class"
                value={primary ? PLATFORM_LABEL[primary.platform] : "-"}
                muted={!primary || primary.platform === "UNKNOWN"}
              />
              <Row
                label="Straightness"
                value={features ? features.straightness.toFixed(2) : "-"}
                muted={!features}
              />
              <Row
                label="Turn rate"
                value={features ? `${features.turn_rate.toFixed(0)} °/s` : "-"}
                muted={!features}
              />
              <Row
                label="Image rate"
                value={features ? `${features.mean_speed.toFixed(2)} fw/s` : "-"}
                muted={!features}
                title="Frame widths per second - a direct measurement."
              />
              <Row
                label="Speed"
                value={
                  speed?.available
                    ? `${speed.speed_ms.toFixed(0)} m/s`
                    : "NOT CALIBRATED"
                }
                muted={!speed?.available}
                title={
                  speed?.detail ??
                  "Absolute speed needs a configured camera field of view."
                }
              />
            </div>
          </div>

          <div className="details-group">
            <div className="details-title">Perception</div>
            <div className="readout">
              <Row
                label="Detector"
                value={system?.detector ?? "-"}
                muted={!system}
              />
              <Row
                label="Source"
                value={system?.video_source ?? "-"}
                muted={!system}
              />
              <Row
                label="Rate"
                value={system ? `${system.fps.toFixed(0)} fps` : "-"}
                muted={!system}
              />
              <Row
                label="Frame"
                value={system ? `${system.frame_index}` : "-"}
                muted={!system}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

import { Dot, Meter, Row } from "../common/Readout";
import { PLATFORM_LABEL } from "../../format";
import type {
  InterceptorState,
  InterceptSolution,
  MissionStatus,
  SystemStatus,
  Target,
} from "../../types";

interface Props {
  system: SystemStatus | null;
  mission: MissionStatus | null;
  primary: Target | null;
  connected: boolean;
  intercept: InterceptSolution | null;
  interceptor: InterceptorState | null;
}

/**
 * The canister status column.
 *
 * Every value comes straight from backend telemetry — nothing is derived
 * locally, so the panel cannot disagree with the mission state machine.
 */
export function StatusPanel({
  system,
  mission,
  primary,
  connected,
  intercept,
  interceptor,
}: Props) {
  const confidence = primary ? Math.round(primary.confidence * 100) : 0;
  const trajectory = primary?.trajectory ?? null;
  const speed = primary?.speed ?? null;
  const flying = Boolean(interceptor?.active);

  return (
    <>
      {/* ---------------- target ---------------- */}
      <div className="card">
        <div className="card-title">Target</div>

        <div className={`target-id${primary ? "" : " is-empty"}`}>
          {primary ? primary.target_id : "NO TARGET"}
        </div>
        <div className="platform-line">
          {primary ? PLATFORM_LABEL[primary.platform] : "—"}
        </div>

        <div style={{ marginTop: "0.85rem" }} className="readout">
          <Row
            label="Class"
            value={primary ? primary.class.toUpperCase() : "—"}
            muted={!primary}
          />
          <div>
            <Row
              label="Confidence"
              value={primary ? `${confidence}%` : "—"}
              muted={!primary}
            />
            <Meter value={confidence / 100} />
          </div>
          <Row
            label="Track"
            value={primary ? (primary.tracking ? "ACTIVE" : "TENTATIVE") : "—"}
            muted={!primary}
          />
          <Row
            label="Held"
            value={primary ? `${primary.track_duration.toFixed(1)}s` : "—"}
            muted={!primary}
          />
        </div>
      </div>

      {/* ---------------- platform + speed ---------------- */}
      <div className="card">
        <div className="card-title">
          Platform &amp; Speed <span className="tag">Estimate</span>
        </div>
        <div className="readout">
          <Row
            label="Airframe"
            value={primary ? PLATFORM_LABEL[primary.platform] : "—"}
            muted={!primary || primary.platform === "UNKNOWN"}
          />
          <Row
            label="Image rate"
            value={
              trajectory?.velocity
                ? `${trajectory.velocity.speed.toFixed(2)} fw/s`
                : "—"
            }
            muted={!trajectory?.velocity}
            title="Frame widths per second — a direct measurement"
          />
          <Row
            label="Speed"
            value={
              speed?.available
                ? `${speed.speed_ms.toFixed(0)} m/s · ${speed.speed_kmh.toFixed(0)} km/h`
                : "NOT CALIBRATED"
            }
            muted={!speed?.available}
            title={speed?.detail}
          />
          <Row
            label="Range"
            value={speed?.available ? `${speed.range_m.toFixed(0)} m` : "—"}
            muted={!speed?.available}
            title={speed?.detail}
          />
          {speed?.available && !speed.plausible && (
            <div className="note is-bad">Outside typical envelope for class.</div>
          )}
        </div>
      </div>

      {/* ---------------- trajectory + intercept ---------------- */}
      <div className="card">
        <div className="card-title">
          Trajectory &amp; Intercept <span className="tag">Estimate</span>
        </div>
        <div className="readout">
          <Row
            label="Predicted path"
            value={
              trajectory?.valid
                ? `${Math.round(trajectory.confidence * 100)}% conf`
                : "—"
            }
            muted={!trajectory?.valid}
          />
          <Row
            label="Horizon"
            value={trajectory?.valid ? `${trajectory.horizon.toFixed(1)}s` : "—"}
            muted={!trajectory?.valid}
            title="Scaled by airframe class — a fixed-wing holds its course further"
          />
          <Row
            label={flying ? "Time to impact" : "Intercept in"}
            value={
              flying && interceptor
                ? `${interceptor.time_to_intercept.toFixed(1)}s`
                : intercept?.feasible
                  ? `${intercept.time_to_intercept.toFixed(1)}s`
                  : "NO SOLUTION"
            }
            muted={!flying && !intercept?.feasible}
          />
          <Row
            label="Interceptor"
            value={flying && interceptor ? interceptor.phase : "STOWED"}
            muted={!flying}
          />
        </div>
      </div>

      {/* ---------------- canister ---------------- */}
      <div className="card">
        <div className="card-title">Canister 01</div>
        <div className="readout">
          <Dot
            ok={Boolean(system?.sensor_online)}
            label={system?.sensor_online ? "Sensor online" : "Sensor offline"}
          />
          <Dot
            ok={Boolean(system?.detector_ready)}
            label={
              system?.detector_ready
                ? `Detector ready · ${system.detector}`
                : "Detector initialising"
            }
          />
          <Dot
            ok={connected}
            label={connected ? "Link established" : "Link lost"}
          />

          <div style={{ marginTop: "0.35rem", display: "grid", gap: "0.65rem" }}>
            <Row
              label="Rate"
              value={system ? `${system.fps.toFixed(0)} FPS` : "—"}
            />
            <Row
              label="Actuator"
              value={
                mission?.state === "ACTUATED"
                  ? "FIRED (SIM)"
                  : mission?.state === "AUTHORIZED"
                    ? "ACTUATING"
                    : "SAFE"
              }
              muted={mission?.state !== "ACTUATED"}
            />
          </div>
        </div>
      </div>
    </>
  );
}

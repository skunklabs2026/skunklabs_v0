import { Meter, Row } from "../common/Readout";
import { PLATFORM_LABEL } from "../../format";
import type { MissionState, Target } from "../../types";

interface Props {
  primary: Target | null;
  state: MissionState;
}

/** Mission states in which the demo confirmation criteria have been satisfied. */
const CRITERIA_MET: ReadonlySet<MissionState> = new Set<MissionState>([
  "THREAT_CONFIRMED",
  "FOLLOWING",
  "AWAITING_AUTHORIZATION",
  "AUTHORIZED",
  "ACTUATED",
]);

/**
 * The target the canister is acting on.
 *
 * Six fields, in the order an operator asks for them: who, what, how sure,
 * how long, how solid, and does it meet the criteria. Everything else -
 * airframe kinematics, projection maths, detector internals - lives behind
 * DETAILS, because it is engineering information, not operational
 * information.
 */
export function TargetPanel({ primary, state }: Props) {
  const confidence = primary ? Math.round(primary.confidence * 100) : 0;
  const stability = primary?.projection?.stability ?? "UNAVAILABLE";
  const criteriaMet = CRITERIA_MET.has(state);

  // "Track" describes how solidly the track is held, which is a different
  // question from whether it exists: a target can be tracked but jittering.
  const trackQuality = !primary
    ? "-"
    : !primary.tracking
      ? "TENTATIVE"
      : stability === "STABLE"
        ? "STABLE"
        : stability === "SETTLING"
          ? "SETTLING"
          : "ACTIVE";

  return (
    <div className="card">
      <div className="card-title">Target</div>

      <div className={`target-id${primary ? "" : " is-empty"}`}>
        {primary ? primary.target_id : "NO TARGET"}
      </div>
      <div className="platform-line">
        {primary ? PLATFORM_LABEL[primary.platform] : "Searching"}
      </div>

      <div className="readout readout-spaced">
        <Row
          label="Class"
          value={primary ? primary.class.toUpperCase() : "-"}
          muted={!primary}
        />
        <div>
          <Row
            label="Confidence"
            value={primary ? `${confidence}%` : "-"}
            muted={!primary}
          />
          <Meter value={confidence / 100} />
        </div>
        <Row
          label="Track age"
          value={primary ? `${primary.track_duration.toFixed(1)} s` : "-"}
          muted={!primary}
        />
        <Row label="Track" value={trackQuality} muted={!primary} />
        <Row
          label="Threat criteria"
          value={primary ? (criteriaMet ? "MET" : "EVALUATING") : "-"}
          muted={!primary}
          title="Transparent V0 demo criteria: class, mean confidence and dwell time."
        />
      </div>
    </div>
  );
}

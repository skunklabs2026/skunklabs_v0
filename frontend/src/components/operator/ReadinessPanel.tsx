import type { CSSProperties } from "react";
import { CONDITION_LABEL, READINESS_COLOR, READINESS_LABEL } from "../../format";
import type { EngagementReadiness, LauncherStatus } from "../../types";

interface Props {
  readiness: EngagementReadiness | null;
  launcher: LauncherStatus | null;
}

/**
 * Engagement readiness — the six preconditions and the state they derive.
 *
 * Every condition is shown whatever the verdict, met or not. A checklist that
 * only lists failures gives an operator no way to tell "everything passed"
 * from "nothing was evaluated", and this panel is the one place they can see
 * exactly why the AUTHORIZE control is or is not available.
 */
export function ReadinessPanel({ readiness, launcher }: Props) {
  const state = readiness?.state ?? "NOT_READY";
  const conditions = readiness?.conditions ?? [];

  return (
    <div className="card">
      <div className="card-title">Engagement Readiness</div>

      <div
        className="readiness-state"
        style={{ "--state-color": READINESS_COLOR[state] } as CSSProperties}
      >
        {READINESS_LABEL[state]}
      </div>
      <div className="readiness-detail">{readiness?.detail ?? "Evaluating…"}</div>

      <ul className="conditions">
        {conditions.map((condition) => (
          <li
            key={condition.name}
            className={`condition${condition.met ? " is-met" : ""}`}
            title={condition.detail}
          >
            <span className="condition-mark" aria-hidden="true">
              {condition.met ? "✓" : "○"}
            </span>
            <span className="condition-name">
              {CONDITION_LABEL[condition.name] ?? condition.name}
            </span>
          </li>
        ))}
      </ul>

      {launcher && (
        <div className="launcher-line" title={launcher.detail}>
          <span>Launcher</span>
          <span className="launcher-state">
            {launcher.state}
            {launcher.simulated && <span className="tag">Simulated</span>}
          </span>
        </div>
      )}

      {/* The command identifier is what correlates this engagement with a
          launcher log — the field a hardware-in-the-loop test reads first. */}
      {launcher?.last_command_id && (
        <div className="launcher-command">CMD {launcher.last_command_id}</div>
      )}
    </div>
  );
}

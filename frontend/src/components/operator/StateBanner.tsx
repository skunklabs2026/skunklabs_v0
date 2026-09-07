import type { CSSProperties } from "react";
import { STATE_COLOR, STATE_LABEL, URGENT_STATES } from "../../format";
import type { MissionState, MissionStatus } from "../../types";

interface Props {
  state: MissionState;
  mission: MissionStatus | null;
  onAuthorize: () => void;
}

/**
 * The large state banner and the AUTHORIZE control.
 *
 * The button's enabled state comes straight from `mission.can_authorize`,
 * which the backend state machine owns. The UI never decides for itself that
 * authorization is allowed.
 */
export function StateBanner({ state, mission, onAuthorize }: Props) {
  const armed = Boolean(mission?.can_authorize);
  const done = state === "AUTHORIZED" || state === "ACTUATED";

  return (
    <div
      className={`banner${URGENT_STATES.has(state) ? " is-urgent" : ""}`}
      style={
        {
          "--state-color": STATE_COLOR[state],
          "--progress": mission?.progress ?? 0,
        } as CSSProperties
      }
    >
      <div style={{ minWidth: 0 }}>
        <div className="banner-state">{STATE_LABEL[state]}</div>
        <div className="banner-detail" title={mission?.detail}>
          {mission?.detail ?? "Connecting to canister…"}
        </div>
      </div>

      <button
        type="button"
        className={`authorize${armed ? " is-armed" : ""}`}
        disabled={!armed}
        onClick={onAuthorize}
      >
        {done ? "Authorized" : "Authorize"}
      </button>
    </div>
  );
}

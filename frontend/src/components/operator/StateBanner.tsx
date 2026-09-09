import type { CSSProperties } from "react";
import { STATE_COLOR, STATE_LABEL, URGENT_STATES } from "../../format";
import type { EngagementReadiness, MissionState, MissionStatus } from "../../types";

interface Props {
  state: MissionState;
  mission: MissionStatus | null;
  readiness: EngagementReadiness | null;
  onAuthorize: () => void;
}

/**
 * The large state banner and the AUTHORIZE control.
 *
 * The button's enabled state comes straight from `mission.can_authorize`,
 * which the backend state machine owns. The UI never decides for itself that
 * authorization is allowed.
 *
 * When the control is unavailable the banner says *why*, taken from the
 * readiness gate. "Authorize (disabled)" with no explanation is the kind of
 * dead end that makes an operator distrust the whole console.
 */
export function StateBanner({ state, mission, readiness, onAuthorize }: Props) {
  const armed = Boolean(mission?.can_authorize);
  const issued = state === "AUTHORIZED" || state === "ACTUATED";

  // The readiness detail is more specific than the mission detail whenever
  // the mission is waiting on a precondition rather than on time.
  const blocked = Boolean(readiness?.blocking.length) && !armed && !issued;
  const detail =
    blocked && readiness
      ? readiness.detail
      : (mission?.detail ?? "Connecting to canister…");

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
        <div className="banner-detail" title={detail}>
          {detail}
        </div>
      </div>

      <button
        type="button"
        className={`authorize${armed ? " is-armed" : ""}`}
        disabled={!armed}
        onClick={onAuthorize}
      >
        {issued ? "Authorized" : "Authorize"}
      </button>
    </div>
  );
}

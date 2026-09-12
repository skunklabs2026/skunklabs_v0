import { PHASE_LABEL } from "../../format";
import type { MissionStatus, PhaseProgress } from "../../types";

interface Props {
  mission: MissionStatus | null;
}

/**
 * The permanent mission sequence:
 *
 *   SEARCH → DETECT → TRACK → CONFIRM → FOLLOW → AUTHORIZE → LAUNCH
 *
 * The steps arrive fully resolved in `mission.phases`, computed by the
 * backend state machine. This component decides nothing about progression -
 * it draws what it is given. That is the whole reason the timeline lives in
 * the telemetry contract rather than being derived from `mission.state` here:
 * two independent state machines would eventually disagree, on screen, in
 * front of someone.
 */
export function MissionTimeline({ mission }: Props) {
  const phases: PhaseProgress[] = mission?.phases ?? [];

  if (phases.length === 0) {
    return (
      <div className="timeline is-waiting" aria-hidden="true">
        <span className="timeline-waiting">Awaiting canister telemetry…</span>
      </div>
    );
  }

  return (
    <ol
      className="timeline"
      aria-label="Mission sequence"
      // The active step is announced, so the sequence is followable without
      // relying on colour alone.
      aria-live="polite"
    >
      {phases.map((step) => {
        const state = step.status.toLowerCase();
        return (
          <li
            key={step.phase}
            className={`phase is-${state}`}
            aria-current={step.status === "ACTIVE" ? "step" : undefined}
          >
            <span className="phase-mark" aria-hidden="true">
              {step.status === "COMPLETE"
                ? "✓"
                : step.status === "ACTIVE"
                  ? "●"
                  : "○"}
            </span>
            <span className="phase-name">{PHASE_LABEL[step.phase]}</span>
            {step.status === "ACTIVE" && (
              <span
                className="phase-progress"
                style={{ transform: `scaleX(${step.progress})` }}
                aria-hidden="true"
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

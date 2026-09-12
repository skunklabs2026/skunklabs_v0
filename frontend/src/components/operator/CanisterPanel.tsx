import { StatusDot, type Tone } from "../common/Readout";
import { UNKNOWN_SUBSYSTEM_STATES } from "../../format";
import type { CanisterStatus, Subsystem, SubsystemId } from "../../types";

interface Props {
  canister: CanisterStatus | null;
  connected: boolean;
}

/**
 * The subsystems shown on the operator console, in this order.
 *
 * Power and temperature are deliberately included even though V0 can only
 * report NOT CONNECTED and N/A for them. Showing the empty slot is how the
 * panel stays honest about what a real canister would report and this one
 * cannot - hiding them would quietly imply the list is complete.
 */
const SHOWN: readonly SubsystemId[] = [
  "SENSOR",
  "PERCEPTION",
  "TRACKER",
  "COMPUTE",
  "LINK",
  "LAUNCHER",
  "INTERCEPTOR",
  "POWER",
  "TEMPERATURE",
];

function tone(subsystem: Subsystem): Tone {
  if (UNKNOWN_SUBSYSTEM_STATES.has(subsystem.state)) return "unknown";
  return subsystem.nominal ? "ok" : "bad";
}

export function CanisterPanel({ canister, connected }: Props) {
  const byId = new Map((canister?.subsystems ?? []).map((s) => [s.id, s]));
  const rows = SHOWN.map((id) => byId.get(id)).filter(
    (s): s is Subsystem => s !== undefined,
  );

  return (
    <div className="card">
      <div className="card-title">{canister?.canister_id ?? "Canister"}</div>

      <div className="subsystems">
        {rows.map((subsystem) => (
          <div
            key={subsystem.id}
            className={`subsystem is-${tone(subsystem)}`}
            title={subsystem.detail}
          >
            <StatusDot tone={tone(subsystem)} />
            <span className="subsystem-name">{subsystem.label}</span>
            <span className="subsystem-state">{subsystem.state}</span>
          </div>
        ))}

        {/* The operator's own link to the canister is not a canister
            subsystem - it is the console reporting on itself, so it sits
            below the list rather than inside it. */}
        <div className={`subsystem is-${connected ? "ok" : "bad"}`}>
          <StatusDot tone={connected ? "ok" : "bad"} />
          <span className="subsystem-name">Console</span>
          <span className="subsystem-state">
            {connected ? "CONNECTED" : "RECONNECTING"}
          </span>
        </div>
      </div>
    </div>
  );
}

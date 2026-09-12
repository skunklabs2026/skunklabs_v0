import type { SimulatedInterceptor } from "../../scenario/contract";
import { INTERCEPTOR_LABEL, INTERCEPTOR_TONE } from "../../scenario/format";
import { Led } from "../shell/Tone";
import { toneClass } from "../shell/toneClass";

/** Each simulated interceptor, the threat it is assigned to, and its status. */
export function InterceptorList({
  interceptors,
}: {
  interceptors: SimulatedInterceptor[];
}) {
  if (interceptors.length === 0) {
    return <p className="c-empty">No interceptors assigned.</p>;
  }
  return (
    <ul className="c-int-list">
      {interceptors.map((interceptor) => {
        const tone = INTERCEPTOR_TONE[interceptor.state];
        return (
          <li key={interceptor.id} data-state={interceptor.state}>
            <span className="c-int-id">{interceptor.id}</span>
            <span className="c-int-target">→ {interceptor.track_id}</span>
            <span className={`c-int-status ${toneClass(tone)}`}>
              <Led tone={tone} />
              {INTERCEPTOR_LABEL[interceptor.state]}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

import { useEffect, useRef } from "react";
import { formatClock } from "../../format";
import type { MissionEvent } from "../../types";

interface Props {
  events: MissionEvent[];
}

/**
 * The operator event log.
 *
 * Every entry carries a structured `code` alongside its prose, and the code
 * is what is shown:
 *
 *   18:40:11  OBJECT_DETECTED
 *   18:40:12  TRACK_CREATED            UAV-001
 *   18:40:19  LAUNCH_COMMAND_ISSUED    UAV-001
 *   18:40:19  ACTUATOR_ACKNOWLEDGED    UAV-001
 *
 * That is a deliberate change from showing the sentence. A column of codes
 * scans as a sequence of events - which is what an operator watching a run
 * and an engineer reading a mission report both need. The prose is still
 * there, on hover, for when the code is not enough.
 */
export function EventLog({ events }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  // Follow the tail, but stop auto-scrolling if the operator has scrolled up
  // to read something - yanking the view away mid-read is hostile.
  useEffect(() => {
    const node = scrollRef.current;
    if (node && pinnedRef.current) {
      node.scrollTop = node.scrollHeight;
    }
  }, [events]);

  const handleScroll = () => {
    const node = scrollRef.current;
    if (!node) return;
    const distanceFromBottom =
      node.scrollHeight - node.scrollTop - node.clientHeight;
    pinnedRef.current = distanceFromBottom < 24;
  };

  return (
    <div className="card log">
      <div className="card-title">Event Log</div>
      <div className="log-scroll" ref={scrollRef} onScroll={handleScroll}>
        {events.length === 0 && (
          <div className="log-entry">
            <span className="log-time">--:--:--</span>
            <span className="log-code">AWAITING_TELEMETRY</span>
          </div>
        )}
        {events.map((event, index) => (
          <div
            key={`${event.timestamp}-${index}`}
            className={`log-entry kind-${event.kind}`}
            title={event.message}
          >
            <span className="log-time">{formatClock(event.timestamp)}</span>
            <span className="log-code">{event.code}</span>
            <span className="log-target">{event.target_id ?? ""}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

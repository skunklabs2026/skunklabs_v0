import { useEffect, useRef } from "react";
import { formatClock } from "../../format";
import type { MissionEvent } from "../../types";

interface Props {
  events: MissionEvent[];
}

/**
 * The operator event log.
 *
 * The reference document requires every important event to be timestamped and
 * visible: detection, track acquired/lost, threat state, authorization and
 * actuation. This is that record, streamed live from the backend.
 */
export function EventLog({ events }: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinnedRef = useRef(true);

  // Follow the tail, but stop auto-scrolling if the operator has scrolled up
  // to read something — yanking the view away mid-read is hostile.
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
            <span>Awaiting telemetry…</span>
          </div>
        )}
        {events.map((event, index) => (
          <div
            key={`${event.timestamp}-${index}`}
            className={`log-entry kind-${event.kind}`}
          >
            <span className="log-time">{formatClock(event.timestamp)}</span>
            <span>{event.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

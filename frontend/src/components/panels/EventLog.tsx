import { useEffect, useRef } from "react";
import { formatClock } from "../../scenario/format";
import { useScenario } from "../../scenario/hooks";

/** What happened, in order. Straight from the backend's event list. */
export function EventLog() {
  const events = useScenario().snapshot?.events ?? [];
  const list = useRef<HTMLOListElement>(null);
  const count = events.length;

  useEffect(() => {
    const element = list.current;
    if (element) element.scrollTop = element.scrollHeight;
  }, [count]);

  return (
    <section className="c-panel c-log" aria-label="Event log">
      <div className="c-panel-head">
        <h2 className="c-panel-title">Event log</h2>
        <span className="c-count">{count}</span>
      </div>
      {count === 0 ? (
        <p className="c-empty">No events yet.</p>
      ) : (
        <ol ref={list}>
          {events.map((event, i) => (
            <li key={`${event.timestamp}-${i}`}>
              <time>{formatClock(event.timestamp)}</time>
              <span>{event.message}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

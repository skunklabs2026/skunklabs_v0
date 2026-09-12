import type { Connection } from "../../scenario/store";

/** Covers a view until the first snapshot arrives. */
export function ConnectionOverlay({ connection }: { connection: Connection }) {
  return (
    <div className="c-overlay" role="status">
      {connection === "offline" ? (
        <div>
          Backend offline
          <br />
          <span className="c-dim">Start it with `make demo` - retrying…</span>
        </div>
      ) : (
        <div>Connecting to the launcher node…</div>
      )}
    </div>
  );
}

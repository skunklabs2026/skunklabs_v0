/** Shared label/value primitives used by both screens. */

interface RowProps {
  label: string;
  value: string;
  muted?: boolean;
  title?: string;
}

/** One label-left / value-right line. */
export function Row({ label, value, muted = false, title }: RowProps) {
  return (
    <div className="readout-row">
      <span className="readout-label">{label}</span>
      <span
        className={`readout-value${muted ? " is-muted" : ""}`}
        title={title ?? value}
      >
        {value}
      </span>
    </div>
  );
}

/** A status dot with a caption. */
export function Dot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="dot-row">
      <span className={`dot ${ok ? "is-ok" : "is-bad"}`} />
      <span>{label}</span>
    </div>
  );
}

/**
 * Three-state status dot.
 *
 * "unknown" is a first-class tone, not a shade of bad. A canister with no
 * power monitor is not unhealthy — it has nothing to report — and colouring
 * that red would train an operator to ignore red.
 */
export type Tone = "ok" | "bad" | "unknown";

export function StatusDot({ tone }: { tone: Tone }) {
  return <span className={`dot is-${tone}`} aria-hidden="true" />;
}

/** A 0..1 horizontal meter. */
export function Meter({ value }: { value: number }) {
  return (
    <div className="meter">
      <div
        className="meter-fill"
        style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
      />
    </div>
  );
}

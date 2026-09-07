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

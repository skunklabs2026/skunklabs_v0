import { Row } from "../common/Readout";

interface Props {
  available: string[];
  active: string;
  threshold: number;
  busy: boolean;
  onSelect: (detector: string) => void;
  onThreshold: (value: number) => void;
}

const BLURB: Record<string, string> = {
  motion:
    "Background subtraction. No model weights. Best for a fixed camera against sky.",
  yolo: "YOLO26n neural detector. Use for real-world, handheld or cluttered footage.",
};

/** Detector selection plus the live confidence threshold. */
export function DetectorChoice({
  available,
  active,
  threshold,
  busy,
  onSelect,
  onThreshold,
}: Props) {
  return (
    <>
      <div className="detector-choice">
        {available.map((name) => (
          <button
            key={name}
            type="button"
            disabled={busy}
            className={`detector-card${active === name ? " is-on" : ""}`}
            onClick={() => onSelect(name)}
          >
            <span className="detector-name">{name}</span>
            <span className="detector-blurb">{BLURB[name] ?? ""}</span>
          </button>
        ))}
      </div>

      <div className="threshold">
        <div className="threshold-head">
          <Row label="Confidence" value={threshold.toFixed(2)} />
        </div>
        <input
          type="range"
          min={0.05}
          max={0.9}
          step={0.05}
          value={threshold}
          disabled={busy}
          aria-label="Detection confidence threshold"
          onChange={(event) => onThreshold(Number(event.target.value))}
        />
        <div className="note">
          Lower it if a small or distant target is missed; raise it if the frame
          fills with false detections.
        </div>
      </div>
    </>
  );
}

import { useState } from "react";
import { DetectorChoice } from "./DetectorChoice";

interface Props {
  available: string[];
  active: string;
  threshold: number;
  busy: boolean;
  onSelect: (detector: string) => void;
  onThreshold: (value: number) => void;
}

/**
 * Perception settings - detector choice and confidence threshold.
 *
 * Collapsed by default, and that is the point of this component existing at
 * all. Which detector is running is an engineering decision about how the
 * canister sees; it is not part of operating a canister, and putting it on
 * the front page made the whole product read as a computer-vision demo.
 *
 * It is still one click away, because the right threshold is a property of
 * the *footage* rather than of the code, and being able to tune it while
 * watching the detection count is the difference between "the model does not
 * work on my video" and "the threshold was too high".
 */
export function AdvancedPanel(props: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="advanced">
      <button
        type="button"
        className="advanced-toggle"
        aria-expanded={open}
        onClick={() => setOpen((was) => !was)}
      >
        <span>Advanced · Perception settings</span>
        <span className="advanced-chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
      </button>

      {open ? (
        <div className="advanced-body">
          <DetectorChoice {...props} />
        </div>
      ) : (
        <div className="advanced-summary">
          Perception module <b>{props.active}</b> · threshold{" "}
          {props.threshold.toFixed(2)}
        </div>
      )}
    </div>
  );
}

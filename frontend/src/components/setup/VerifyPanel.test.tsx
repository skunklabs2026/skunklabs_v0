import { render, screen, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, it, expect } from "vitest";
import { VerifyPanel } from "./VerifyPanel";
import { makeSystem, makeDetection } from "../../test/factories";

/** The component's own props, so a fixture cannot drift from it. */
type Props = ComponentProps<typeof VerifyPanel>;

const base: Props = {
  system: makeSystem(),
  detection: makeDetection(),
  sourceName: "demo_drone.mp4",
  live: true,
};

const verify = (props: Partial<Props> = {}) =>
  render(<VerifyPanel {...base} {...props} />).container;

function rowValue(container: HTMLElement, label: string): string {
  const labelEl = within(container).getByText(label);
  return labelEl.parentElement?.textContent?.replace(label, "").trim() ?? "";
}

describe("VerifyPanel", () => {
  it("names the source being verified", () => {
    expect(rowValue(verify(), "Source")).toBe("demo_drone.mp4");
  });

  it("dashes the source before one is chosen", () => {
    expect(rowValue(verify({ sourceName: null }), "Source")).toBe("—");
  });

  it("shows frames processed and the rate — evidence footage is flowing", () => {
    const container = verify({
      system: makeSystem({ fps: 24.8 }),
      detection: makeDetection({ frames_processed: 600 }),
    });
    expect(rowValue(container, "Frames")).toBe("600 @ 25 fps");
  });

  it("dashes frames with no system status", () => {
    expect(rowValue(verify({ system: null }), "Frames")).toBe("—");
  });

  it("counts frames as 0 when detection stats have not arrived", () => {
    expect(rowValue(verify({ detection: null }), "Frames")).toBe("0 @ 25 fps");
  });

  it("shows cumulative and current detections", () => {
    const container = verify({
      detection: makeDetection({ detections_total: 459, detections_last_frame: 2 }),
    });
    expect(rowValue(container, "Detections")).toBe("459 / 2 now");
  });

  it("shows zeroes rather than dashes before anything is detected", () => {
    expect(rowValue(verify({ detection: null }), "Detections")).toBe("0 / 0 now");
    expect(rowValue(verify({ detection: null }), "Active tracks")).toBe("0");
  });

  it("reports active tracks and inference latency", () => {
    const container = verify({
      detection: makeDetection({ active_tracks: 3, latency_ms: 4.2 }),
    });
    expect(rowValue(container, "Active tracks")).toBe("3");
    expect(rowValue(container, "Inference")).toBe("4.2 ms");
  });

  it("dashes latency when it has not been measured", () => {
    expect(
      rowValue(
        verify({ detection: makeDetection({ latency_ms: 0 }) }),
        "Inference",
      ),
    ).toBe("—");
  });

  it("chips each class seen, with its count", () => {
    const container = verify({
      detection: makeDetection({
        classes: [
          { name: "uav", count: 459 },
          { name: "bird", count: 3 },
        ],
      }),
    });
    const chips = container.querySelectorAll(".chip");
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveTextContent("uav 459");
    expect(chips[1]).toHaveTextContent("bird 3");
  });

  // The actionable case: footage is playing but nothing is being found.
  it("suggests what to change when a live run detects nothing", () => {
    verify({ live: true, detection: makeDetection({ classes: [] }) });
    expect(
      screen.getByText(/Nothing detected yet — try the other detector/),
    ).toBeInTheDocument();
  });

  it("stays quiet when the pipeline is not running yet", () => {
    verify({ live: false, detection: makeDetection({ classes: [] }) });
    expect(screen.queryByText(/Nothing detected yet/)).not.toBeInTheDocument();
  });

  it("stays quiet once something has been detected", () => {
    verify({ live: true });
    expect(screen.queryByText(/Nothing detected yet/)).not.toBeInTheDocument();
  });
});

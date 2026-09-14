import { render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, it, expect } from "vitest";
import { VideoStage } from "./VideoStage";
import {
  makeSystem,
  makeTarget,
  makeIntercept,
  makeInterceptor,
} from "../../test/factories";

/** The component's own props, so a fixture cannot drift from it. */
type Props = ComponentProps<typeof VideoStage>;

const base: Props = {
  system: makeSystem(),
  targets: [makeTarget()],
  state: "TRACKING" as const,
  intercept: makeIntercept(),
  interceptor: null,
  launching: false,
  hasTelemetry: true,
};

const stage = (props: Partial<Props> = {}) =>
  render(<VideoStage {...base} {...props} />).container;

describe("VideoStage", () => {
  it("points the feed at the MJPEG endpoint", () => {
    stage();
    expect(screen.getByAltText("Sensor feed")).toHaveAttribute("src", "/api/video");
  });

  // The frame is locked to the source aspect so the 0..1 overlays land on the
  // pixels they describe; letterboxing happens outside that box.
  it("locks the frame to the reported aspect ratio", () => {
    const frame = stage().querySelector(".frame") as HTMLElement;
    expect(frame.style.aspectRatio).toBe("960 / 540");
  });

  it("falls back to 16:9 before the first frame reports dimensions", () => {
    const frame = stage({ system: null }).querySelector(".frame") as HTMLElement;
    expect(frame.style.aspectRatio).toBe("16 / 9");
  });

  it("falls back to 16:9 rather than 0 when dimensions are zero", () => {
    const frame = stage({
      system: makeSystem({ frame_width: 0, frame_height: 0 }),
    }).querySelector(".frame") as HTMLElement;
    expect(frame.style.aspectRatio).toBe("16 / 9");
  });

  it("summarises source, detector, rate and frame index", () => {
    stage({ system: makeSystem({ fps: 24.6, frame_index: 120 }) });
    expect(
      screen.getByText("file:demo_drone.mp4 · motion · 25 fps · frame 120"),
    ).toBeInTheDocument();
  });

  it("says it is awaiting the feed with no system status", () => {
    stage({ system: null });
    expect(screen.getByText("awaiting feed")).toBeInTheDocument();
  });

  it("renders the four reticle corners", () => {
    const container = stage();
    for (const corner of ["tl", "tr", "bl", "br"]) {
      expect(container.querySelector(`.corner.${corner}`)).toBeInTheDocument();
    }
  });

  it("shows the launch cue only while launching", () => {
    expect(stage({ launching: false }).querySelector(".launch-flash")).toBeNull();

    const cued = stage({ launching: true });
    expect(cued.querySelector(".launch-flash")).toBeInTheDocument();
    expect(screen.getByText("Launch Simulated")).toBeInTheDocument();
  });

  describe("sensor offline notice", () => {
    it("appears when telemetry says the sensor is down", () => {
      stage({ system: makeSystem({ sensor_online: false }), hasTelemetry: true });
      expect(screen.getByText("Sensor Offline")).toBeInTheDocument();
      expect(screen.getByText("Attempting to recover")).toBeInTheDocument();
    });

    // Before any telemetry we do not know the sensor is down — claiming so
    // would be the UI inventing mission state.
    it("stays hidden before the first telemetry frame", () => {
      stage({ system: null, hasTelemetry: false });
      expect(screen.queryByText("Sensor Offline")).not.toBeInTheDocument();
    });

    it("stays hidden while the sensor is online", () => {
      stage({ system: makeSystem({ sensor_online: true }) });
      expect(screen.queryByText("Sensor Offline")).not.toBeInTheDocument();
    });
  });

  it("composes the three overlay layers over the feed", () => {
    const container = stage({
      interceptor: makeInterceptor(),
      state: "AUTHORIZED",
    });
    // Two SVG layers (targets, engagement) plus the HTML label layer.
    expect(container.querySelectorAll("svg.overlay")).toHaveLength(2);
    expect(container.querySelectorAll("div.overlay")).toHaveLength(1);
  });
});

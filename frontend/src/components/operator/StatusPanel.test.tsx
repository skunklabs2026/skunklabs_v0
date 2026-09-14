import { render, within } from "@testing-library/react";
import type { ComponentProps } from "react";
import { describe, it, expect } from "vitest";
import { StatusPanel } from "./StatusPanel";
import {
  makeSystem,
  makeMission,
  makeTarget,
  makeTrajectory,
  makeSpeed,
  makeIntercept,
  makeInterceptor,
} from "../../test/factories";

/** The component's own props, so a fixture cannot drift from it. */
type Props = ComponentProps<typeof StatusPanel>;

const base: Props = {
  system: makeSystem(),
  mission: makeMission(),
  primary: makeTarget(),
  connected: true,
  intercept: makeIntercept(),
  interceptor: null,
};

const panel = (props: Partial<Props> = {}) =>
  render(<StatusPanel {...base} {...props} />).container;

/** The readout rows are label/value pairs; find a value by its label. */
function rowValue(container: HTMLElement, label: string): string {
  const labelEl = within(container).getAllByText(label)[0];
  return labelEl.parentElement?.textContent?.replace(label, "").trim() ?? "";
}

describe("target card", () => {
  it("shows the target id and airframe", () => {
    const container = panel();
    expect(within(container).getByText("UAV-001")).toBeInTheDocument();
    expect(within(container).getAllByText("FIXED-WING").length).toBeGreaterThan(0);
  });

  it("says NO TARGET with an empty modifier when nothing is tracked", () => {
    const container = panel({ primary: null });
    expect(within(container).getByText("NO TARGET")).toBeInTheDocument();
    expect(container.querySelector(".target-id")).toHaveClass("is-empty");
  });

  it("renders the class upper-cased and the confidence as a percentage", () => {
    const container = panel({
      primary: makeTarget({ class: "uav", confidence: 0.856 }),
    });
    expect(rowValue(container, "Class")).toBe("UAV");
    expect(rowValue(container, "Confidence")).toBe("86%");
  });

  it("distinguishes an active track from a tentative one", () => {
    expect(
      rowValue(panel({ primary: makeTarget({ tracking: true }) }), "Track"),
    ).toBe("ACTIVE");
    expect(
      rowValue(panel({ primary: makeTarget({ tracking: false }) }), "Track"),
    ).toBe("TENTATIVE");
  });

  it("shows how long the track has been held", () => {
    expect(
      rowValue(panel({ primary: makeTarget({ track_duration: 3.25 }) }), "Held"),
    ).toBe("3.3s");
  });

  it("dashes every target row when there is no target", () => {
    const container = panel({ primary: null });
    for (const label of ["Class", "Confidence", "Track", "Held"]) {
      expect(rowValue(container, label)).toBe("—");
    }
  });
});

describe("platform and speed card", () => {
  it("shows the inferred speed in both units", () => {
    const container = panel({
      primary: makeTarget({
        speed: makeSpeed({ speed_ms: 34.2, speed_kmh: 123.1 }),
      }),
    });
    expect(rowValue(container, "Speed")).toBe("34 m/s · 123 km/h");
    expect(rowValue(container, "Range")).toBe("108 m");
  });

  // Honesty over a fabricated figure: without a field of view there is no
  // speed to report.
  it("says NOT CALIBRATED rather than inventing a figure", () => {
    const container = panel({
      primary: makeTarget({ speed: makeSpeed({ available: false }) }),
    });
    expect(rowValue(container, "Speed")).toBe("NOT CALIBRATED");
    expect(rowValue(container, "Range")).toBe("—");
  });

  it("flags a speed outside the class envelope", () => {
    const container = panel({
      primary: makeTarget({ speed: makeSpeed({ plausible: false }) }),
    });
    expect(
      within(container).getByText("Outside typical envelope for class."),
    ).toBeInTheDocument();
  });

  it("does not flag a plausible speed", () => {
    const container = panel({
      primary: makeTarget({ speed: makeSpeed({ plausible: true }) }),
    });
    expect(
      within(container).queryByText("Outside typical envelope for class."),
    ).not.toBeInTheDocument();
  });

  it("shows the directly measured image rate", () => {
    expect(rowValue(panel(), "Image rate")).toBe("0.20 fw/s");
  });

  it("dashes the image rate with no velocity", () => {
    const container = panel({
      primary: makeTarget({ trajectory: makeTrajectory({ velocity: null }) }),
    });
    expect(rowValue(container, "Image rate")).toBe("—");
  });

  it("handles a target with no speed estimate at all", () => {
    const container = panel({ primary: makeTarget({ speed: null }) });
    expect(rowValue(container, "Speed")).toBe("NOT CALIBRATED");
  });
});

describe("trajectory and intercept card", () => {
  it("shows prediction confidence and horizon", () => {
    const container = panel({
      primary: makeTarget({
        trajectory: makeTrajectory({ confidence: 0.85, horizon: 2 }),
      }),
    });
    expect(rowValue(container, "Predicted path")).toBe("85% conf");
    expect(rowValue(container, "Horizon")).toBe("2.0s");
  });

  it("dashes both when the fit is not valid", () => {
    const container = panel({
      primary: makeTarget({ trajectory: makeTrajectory({ valid: false }) }),
    });
    expect(rowValue(container, "Predicted path")).toBe("—");
    expect(rowValue(container, "Horizon")).toBe("—");
  });

  it("shows the predicted intercept time before launch", () => {
    const container = panel({
      intercept: makeIntercept({ time_to_intercept: 1.44 }),
    });
    expect(within(container).getByText("Intercept in")).toBeInTheDocument();
    expect(rowValue(container, "Intercept in")).toBe("1.4s");
  });

  it("says NO SOLUTION when the intercept is infeasible", () => {
    const container = panel({ intercept: makeIntercept({ feasible: false }) });
    expect(rowValue(container, "Intercept in")).toBe("NO SOLUTION");
  });

  it("handles no intercept estimate at all", () => {
    expect(rowValue(panel({ intercept: null }), "Intercept in")).toBe(
      "NO SOLUTION",
    );
  });

  // Once in flight the label and the source of truth both change.
  it("switches to time-to-impact from the interceptor once flying", () => {
    const container = panel({
      intercept: makeIntercept({ time_to_intercept: 9 }),
      interceptor: makeInterceptor({ time_to_intercept: 0.7 }),
    });
    expect(within(container).getByText("Time to impact")).toBeInTheDocument();
    expect(rowValue(container, "Time to impact")).toBe("0.7s");
  });

  it("reports the interceptor as STOWED until it is active", () => {
    expect(rowValue(panel(), "Interceptor")).toBe("STOWED");
    expect(
      rowValue(
        panel({ interceptor: makeInterceptor({ active: false }) }),
        "Interceptor",
      ),
    ).toBe("STOWED");
  });

  it("reports the flight phase while active", () => {
    expect(
      rowValue(
        panel({ interceptor: makeInterceptor({ phase: "FLIGHT" }) }),
        "Interceptor",
      ),
    ).toBe("FLIGHT");
  });
});

describe("canister card", () => {
  it("reports sensor, detector and link as healthy", () => {
    const container = panel();
    expect(within(container).getByText("Sensor online")).toBeInTheDocument();
    expect(
      within(container).getByText("Detector ready · motion"),
    ).toBeInTheDocument();
    expect(within(container).getByText("Link established")).toBeInTheDocument();
  });

  it("reports each of them as unhealthy", () => {
    const container = panel({
      system: makeSystem({ sensor_online: false, detector_ready: false }),
      connected: false,
    });
    expect(within(container).getByText("Sensor offline")).toBeInTheDocument();
    expect(
      within(container).getByText("Detector initialising"),
    ).toBeInTheDocument();
    expect(within(container).getByText("Link lost")).toBeInTheDocument();
  });

  it("copes with no system status", () => {
    const container = panel({ system: null });
    expect(within(container).getByText("Sensor offline")).toBeInTheDocument();
    expect(rowValue(container, "Rate")).toBe("—");
  });

  it("shows the frame rate", () => {
    expect(rowValue(panel({ system: makeSystem({ fps: 24.6 }) }), "Rate")).toBe(
      "25 FPS",
    );
  });

  // The actuator readout is the safety-relevant one: it must say SAFE unless
  // the backend has actually moved past authorization.
  it.each([
    ["SEARCHING", "SAFE"],
    ["TRACKING", "SAFE"],
    ["AWAITING_AUTHORIZATION", "SAFE"],
    ["AUTHORIZED", "ACTUATING"],
    ["ACTUATED", "FIRED (SIM)"],
  ] as const)("reads %s as %s", (state, expected) => {
    expect(rowValue(panel({ mission: makeMission({ state }) }), "Actuator")).toBe(
      expected,
    );
  });

  it("reads SAFE with no mission at all", () => {
    expect(rowValue(panel({ mission: null }), "Actuator")).toBe("SAFE");
  });
});

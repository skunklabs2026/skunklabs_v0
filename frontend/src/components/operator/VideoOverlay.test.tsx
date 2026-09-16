import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { VideoOverlay, EngagementOverlay, TargetLabels } from "./VideoOverlay";
import {
  makeTarget,
  makeTrajectory,
  makeIntercept,
  makeInterceptor,
} from "../../test/factories";
import type { MissionState } from "../../types";

function draw(targets = [makeTarget()], state: MissionState = "TRACKING") {
  return render(<VideoOverlay targets={targets} state={state} />).container;
}

describe("VideoOverlay", () => {
  it("renders a decorative, non-uniformly scaled 0..1 overlay", () => {
    const svg = draw().querySelector("svg")!;
    // The whole alignment strategy rests on these three attributes.
    expect(svg).toHaveAttribute("viewBox", "0 0 1 1");
    expect(svg).toHaveAttribute("preserveAspectRatio", "none");
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });

  it("draws nothing but the canvas when there are no targets", () => {
    const container = draw([]);
    expect(container.querySelectorAll("g")).toHaveLength(0);
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("draws one group per target", () => {
    const container = draw([
      makeTarget({ target_id: "UAV-001" }),
      makeTarget({ target_id: "UAV-002", is_primary: false }),
    ]);
    expect(container.querySelectorAll("g")).toHaveLength(2);
  });

  it("places the box at the normalised bbox, unconverted", () => {
    const container = draw([
      makeTarget({ bbox: { x: 0.25, y: 0.5, width: 0.1, height: 0.2 } }),
    ]);
    const rect = container.querySelector("rect")!;
    expect(rect).toHaveAttribute("x", "0.25");
    expect(rect).toHaveAttribute("y", "0.5");
    expect(rect).toHaveAttribute("width", "0.1");
    expect(rect).toHaveAttribute("height", "0.2");
  });

  describe("colour follows mission state — the banner's language", () => {
    const color = (state: MissionState) =>
      draw([makeTarget()], state).querySelector("rect")!.getAttribute("stroke");

    it.each(["THREAT_CONFIRMED", "FOLLOWING", "AWAITING_AUTHORIZATION"] as const)(
      "%s is the threat colour",
      (state) => expect(color(state)).toBe("var(--threat)"),
    );

    it.each(["AUTHORIZED", "ACTUATED"] as const)(
      "%s is the armed colour",
      (state) => expect(color(state)).toBe("var(--armed)"),
    );

    it("TARGET_LOST goes idle", () =>
      expect(color("TARGET_LOST")).toBe("var(--idle)"));

    it.each(["SEARCHING", "DETECTED", "TRACKING", "ERROR"] as const)(
      "%s is the default track colour",
      (state) => expect(color(state)).toBe("var(--track)"),
    );

    it("a non-primary target is always idle, whatever the state", () => {
      const container = draw(
        [makeTarget({ is_primary: false })],
        "AWAITING_AUTHORIZATION",
      );
      expect(container.querySelector("rect")).toHaveAttribute(
        "stroke",
        "var(--idle)",
      );
    });
  });

  describe("primary-only decoration", () => {
    it("draws four corner brackets and a centre cross on the primary", () => {
      const container = draw([makeTarget({ is_primary: true, trajectory: null })]);
      expect(container.querySelectorAll("path")).toHaveLength(4);
      expect(container.querySelectorAll("line")).toHaveLength(2);
    });

    it("draws none of it on a secondary target", () => {
      const container = draw([makeTarget({ is_primary: false })]);
      expect(container.querySelectorAll("path")).toHaveLength(0);
      expect(container.querySelectorAll("line")).toHaveLength(0);
      expect(container.querySelectorAll("polyline")).toHaveLength(0);
    });

    it("caps the bracket arms so a huge box does not get huge brackets", () => {
      const big = draw([
        makeTarget({ bbox: { x: 0, y: 0, width: 1, height: 1 }, trajectory: null }),
      ]);
      // min(1 * 0.28, 0.035) === 0.035
      expect(big.querySelector("path")).toHaveAttribute(
        "d",
        "M 0.035 0 L 0 0 L 0 0.035",
      );
    });

    it("scales the arms down for a small box", () => {
      const small = draw([
        makeTarget({
          bbox: { x: 0, y: 0, width: 0.1, height: 0.1 },
          trajectory: null,
        }),
      ]);
      // min(0.1 * 0.28, 0.035) === 0.028, below the cap. Parsed rather than
      // string-matched: 0.1 * 0.28 is not exactly 0.028 in binary floating point.
      const [, arm] = small
        .querySelector("path")!
        .getAttribute("d")!
        .match(/^M ([\d.]+) 0 L 0 0 L 0 ([\d.]+)$/)!;
      expect(Number(arm)).toBeCloseTo(0.028, 6);
    });
  });

  describe("trail", () => {
    it("draws the observed trail once there is more than one point", () => {
      const container = draw([
        makeTarget({
          trail: [
            { x: 0.1, y: 0.2 },
            { x: 0.3, y: 0.4 },
          ],
          trajectory: null,
        }),
      ]);
      expect(container.querySelector("polyline")).toHaveAttribute(
        "points",
        "0.1,0.2 0.3,0.4",
      );
    });

    it("omits it for a single point — one point is not a path", () => {
      const container = draw([
        makeTarget({ trail: [{ x: 0.1, y: 0.2 }], trajectory: null }),
      ]);
      expect(container.querySelectorAll("polyline")).toHaveLength(0);
    });
  });

  describe("predicted path", () => {
    it("is dashed, so it cannot be mistaken for the observed trail", () => {
      const container = draw([makeTarget({ trail: [] })]);
      const predicted = container.querySelector("polyline[stroke-dasharray]")!;
      expect(predicted).toBeInTheDocument();
      // Starts at the box centre, then follows the fit.
      expect(predicted.getAttribute("points")).toBe("0.45,0.45 0.5,0.5 0.6,0.5");
    });

    it("is omitted when the fit is not valid", () => {
      const container = draw([
        makeTarget({ trail: [], trajectory: makeTrajectory({ valid: false }) }),
      ]);
      expect(container.querySelector("polyline[stroke-dasharray]")).toBeNull();
    });

    it("is omitted when there is no trajectory at all", () => {
      const container = draw([makeTarget({ trail: [], trajectory: null })]);
      expect(container.querySelector("polyline[stroke-dasharray]")).toBeNull();
    });

    it("fades with prediction confidence", () => {
      const confident = draw([
        makeTarget({ trail: [], trajectory: makeTrajectory({ confidence: 1 }) }),
      ]);
      const unsure = draw([
        makeTarget({ trail: [], trajectory: makeTrajectory({ confidence: 0 }) }),
      ]);
      const opacity = (c: Element) =>
        Number(
          c
            .querySelector("polyline[stroke-dasharray]")!
            .getAttribute("stroke-opacity"),
        );

      expect(opacity(confident)).toBeCloseTo(0.8, 5);
      expect(opacity(unsure)).toBeCloseTo(0.25, 5);
    });
  });
});

describe("EngagementOverlay", () => {
  it("renders nothing with no marker and nothing in flight", () => {
    const { container } = render(
      <EngagementOverlay intercept={null} interceptor={null} state="TRACKING" />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });

  it("renders nothing when the intercept is infeasible", () => {
    const { container } = render(
      <EngagementOverlay
        intercept={makeIntercept({ feasible: false })}
        interceptor={null}
        state="FOLLOWING"
      />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });

  it.each(["THREAT_CONFIRMED", "FOLLOWING", "AWAITING_AUTHORIZATION"] as const)(
    "shows the predicted intercept point in %s",
    (state) => {
      const { container } = render(
        <EngagementOverlay
          intercept={makeIntercept({ point: { x: 0.62, y: 0.44 } })}
          interceptor={null}
          state={state}
        />,
      );
      const circles = container.querySelectorAll("circle");
      expect(circles).toHaveLength(2);
      expect(circles[0]).toHaveAttribute("cx", "0.62");
    },
  );

  it("hides the marker in a state that is not armed", () => {
    const { container } = render(
      <EngagementOverlay
        intercept={makeIntercept()}
        interceptor={null}
        state="TRACKING"
      />,
    );
    // The svg renders (a marker exists) but the marker group does not draw.
    expect(container.querySelectorAll("circle")).toHaveLength(0);
  });

  // Before launch the live estimate is shown; after launch, what the
  // interceptor actually committed to.
  it("prefers the interceptor's committed aim point once flying", () => {
    const { container } = render(
      <EngagementOverlay
        intercept={makeIntercept({ point: { x: 0.1, y: 0.1 } })}
        interceptor={makeInterceptor({ aim_point: { x: 0.9, y: 0.9 } })}
        state="AUTHORIZED"
      />,
    );
    expect(container.querySelector("circle")).toHaveAttribute("cx", "0.9");
  });

  it("draws the flight line, trail and vehicle while in flight", () => {
    const { container } = render(
      <EngagementOverlay
        intercept={null}
        interceptor={makeInterceptor()}
        state="AUTHORIZED"
      />,
    );
    expect(container.querySelector("line")).toBeInTheDocument();
    expect(container.querySelector("polyline")).toHaveAttribute(
      "points",
      "0.5,1 0.52,0.85",
    );
    expect(container.querySelectorAll("circle").length).toBeGreaterThan(0);
  });

  it("omits the flight line when either endpoint is missing", () => {
    const { container } = render(
      <EngagementOverlay
        intercept={null}
        interceptor={makeInterceptor({ launch_point: null })}
        state="AUTHORIZED"
      />,
    );
    expect(container.querySelector("line")).toBeNull();
  });

  it("omits a one-point trail", () => {
    const { container } = render(
      <EngagementOverlay
        intercept={null}
        interceptor={makeInterceptor({ trail: [{ x: 0.5, y: 1 }] })}
        state="AUTHORIZED"
      />,
    );
    expect(container.querySelector("polyline")).toBeNull();
  });

  it("omits the vehicle when it has no position", () => {
    const { container } = render(
      <EngagementOverlay
        intercept={null}
        interceptor={makeInterceptor({ position: null, aim_point: null })}
        state="AUTHORIZED"
      />,
    );
    expect(container.querySelectorAll("circle")).toHaveLength(0);
  });

  it("blooms the vehicle at INTERCEPT", () => {
    const flight = render(
      <EngagementOverlay
        intercept={null}
        interceptor={makeInterceptor({ phase: "FLIGHT", aim_point: null })}
        state="AUTHORIZED"
      />,
    ).container.querySelector("circle")!;
    const hit = render(
      <EngagementOverlay
        intercept={null}
        interceptor={makeInterceptor({ phase: "INTERCEPT", aim_point: null })}
        state="AUTHORIZED"
      />,
    ).container.querySelector("circle")!;

    expect(flight).toHaveAttribute("r", "0.009");
    expect(hit).toHaveAttribute("r", "0.03");
    expect(hit).toHaveAttribute("fill-opacity", "0.35");
  });

  it("draws nothing in flight when the interceptor is inactive", () => {
    const { container } = render(
      <EngagementOverlay
        intercept={null}
        interceptor={makeInterceptor({ active: false })}
        state="AUTHORIZED"
      />,
    );
    expect(container.querySelector("svg")).toBeNull();
  });
});

// A separate HTML layer, because the SVG's non-uniform scaling would distort
// glyphs.
describe("TargetLabels", () => {
  it("renders id, class and rounded confidence", () => {
    const { container } = render(
      <TargetLabels
        targets={[
          makeTarget({ target_id: "UAV-007", class: "uav", confidence: 0.856 }),
        ]}
        state="TRACKING"
      />,
    );
    expect(container.textContent).toContain("UAV-007");
    expect(container.textContent).toContain("uav");
    expect(container.textContent).toContain("86%");
  });

  it("positions by percentage, not pixels", () => {
    const { container } = render(
      <TargetLabels
        targets={[
          makeTarget({ bbox: { x: 0.25, y: 0.5, width: 0.1, height: 0.1 } }),
        ]}
        state="TRACKING"
      />,
    );
    const label = container.querySelector(".overlay > div") as HTMLElement;
    expect(label.style.left).toBe("25%");
    expect(label.style.top).toBe("50%");
  });

  it("dims secondary targets and colours them idle", () => {
    const { container } = render(
      <TargetLabels
        targets={[
          makeTarget({ is_primary: true }),
          makeTarget({ is_primary: false }),
        ]}
        state="AUTHORIZED"
      />,
    );
    const labels = container.querySelectorAll<HTMLElement>(".overlay > div");
    expect(labels[0].style.opacity).toBe("1");
    expect(labels[1].style.opacity).toBe("0.55");
    expect(labels[0].style.color).toBe("var(--armed)");
    expect(labels[1].style.color).toBe("var(--idle)");
  });

  it("renders nothing for no targets", () => {
    const { container } = render(<TargetLabels targets={[]} state="SEARCHING" />);
    expect(container.querySelectorAll(".overlay > div")).toHaveLength(0);
  });
});

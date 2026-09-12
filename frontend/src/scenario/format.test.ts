import { describe, expect, it } from "vitest";
import {
  makeDecisionSnapshot,
  makeInterceptor,
  makeSnapshot,
  makeTrack,
} from "../test/fixtures";
import {
  describeSituation,
  ENGAGEMENT_LABEL,
  formatClock,
  formatElapsed,
  formatElevation,
  formatHeading,
  formatKm,
  MISSION_TONE,
  NODE_LABEL,
  NODE_TONE,
  plural,
  TRACK_TONE,
} from "./format";

describe("formatHeading", () => {
  it.each([
    [72.34, 1, "072.3°"],
    [0, 1, "000.0°"],
    [-10, 1, "350.0°"],
    [359.96, 1, "000.0°"],
    [72.4, 0, "072°"],
    [725, 0, "005°"],
  ])("%s with %s digits → %s", (deg, digits, expected) => {
    expect(formatHeading(deg, digits)).toBe(expected);
  });
});

describe("other formatters", () => {
  it("formats elevation, range, elapsed time and counts", () => {
    expect(formatElevation(12)).toBe("12.0°");
    expect(formatKm(28.44)).toBe("28.4 km");
    expect(formatElapsed(72.4)).toBe("T+01:12");
    expect(formatElapsed(-3)).toBe("T+00:00");
    expect(plural(1, "response")).toBe("1 response");
    expect(plural(2, "response")).toBe("2 responses");
  });

  it("formats an epoch timestamp as local wall-clock time", () => {
    const epoch = new Date(2024, 9, 26, 14, 32, 11).getTime() / 1000;
    expect(formatClock(epoch)).toBe("14:32:11");
  });
});

describe("status vocabulary", () => {
  it("keeps colour and wording in step", () => {
    expect(NODE_LABEL.SIMULATED_LAUNCH).toBe("Launching");
    expect(NODE_TONE.READY).toBe("ready");
    expect(NODE_TONE.STANDBY).toBe("neutral");
    expect(ENGAGEMENT_LABEL.AWAITING_AUTHORIZATION).toBe("Awaiting decision");
    expect(ENGAGEMENT_LABEL.PROPOSED).toBe("Node orienting");
    expect(TRACK_TONE.REACHED_SITE).toBe("alert");
    expect(MISSION_TONE.FAULT).toBe("alert");
  });
});

describe("describeSituation", () => {
  it("names the selected scenario before the demo starts", () => {
    expect(describeSituation(makeSnapshot())).toBe(
      "Scenario 1 - 4 drones approaching from the east. Start the demo when ready.",
    );
  });

  it("leads with decisions the operator owes", () => {
    expect(describeSituation(makeDecisionSnapshot())).toBe(
      "2 responses awaiting operator decision",
    );
  });

  it("reports interceptors in flight once decisions are made", () => {
    const snapshot = makeDecisionSnapshot({
      decision_queue: [],
      interceptors: [makeInterceptor(), makeInterceptor({ id: "INT-002" })],
    });
    expect(describeSituation(snapshot)).toBe("2 simulated interceptors in flight");
  });

  it("distinguishes threats outside the area from those inside it", () => {
    const outside = makeDecisionSnapshot({
      decision_queue: [],
      tracks: [makeTrack({ inside_protected_area: false })],
    });
    expect(describeSituation(outside)).toBe(
      "1 threat inbound, outside the protected area",
    );

    const inside = makeDecisionSnapshot({ decision_queue: [] });
    expect(describeSituation(inside)).toBe("2 threats inside the protected area");
  });

  it("sums up the mission when complete", () => {
    const snapshot = makeDecisionSnapshot({
      state: "COMPLETE",
      running: false,
      decision_queue: [],
      tracks: [
        makeTrack({ status: "INTERCEPTED" }),
        makeTrack({ id: "T-002", status: "INTERCEPTED" }),
        makeTrack({ id: "T-003", status: "REACHED_SITE" }),
      ],
    });
    expect(describeSituation(snapshot)).toBe(
      "Mission complete - 2 of 3 threats intercepted (simulated)",
    );
  });

  it("reports a fault with its reason", () => {
    const snapshot = makeSnapshot({ state: "FAULT", fault: "simulation error" });
    expect(describeSituation(snapshot)).toBe("Fault - simulation error");
    expect(describeSituation(makeSnapshot({ state: "FAULT" }))).toBe("Fault");
  });
});

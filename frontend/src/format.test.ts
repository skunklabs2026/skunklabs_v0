import { describe, it, expect } from "vitest";
import {
  STATE_LABEL,
  STATE_COLOR,
  URGENT_STATES,
  PLATFORM_LABEL,
  formatDuration,
  formatClock,
  basename,
} from "./format";
import type { MissionState, PlatformClass } from "./types";

// The label and colour maps are `Record<MissionState, …>`, so a new state on
// the backend is a type error here rather than an `undefined` on screen. These
// tests pin the runtime half of that: every state the generated union names
// has an entry, and no entry is blank.
const ALL_STATES: MissionState[] = [
  "SEARCHING",
  "DETECTED",
  "TRACKING",
  "THREAT_CONFIRMED",
  "FOLLOWING",
  "AWAITING_AUTHORIZATION",
  "AUTHORIZED",
  "ACTUATED",
  "TARGET_LOST",
  "ERROR",
];

describe("state maps", () => {
  it.each(ALL_STATES)("%s has a non-empty label and colour", (state) => {
    expect(STATE_LABEL[state]).toBeTruthy();
    expect(STATE_COLOR[state]).toMatch(/^var\(--/);
  });

  it("covers exactly the known states", () => {
    expect(Object.keys(STATE_LABEL).sort()).toEqual([...ALL_STATES].sort());
    expect(Object.keys(STATE_COLOR).sort()).toEqual([...ALL_STATES].sort());
  });

  it("marks authorization as the one state that demands attention", () => {
    expect(URGENT_STATES.has("AWAITING_AUTHORIZATION")).toBe(true);
    expect(URGENT_STATES.has("TRACKING")).toBe(false);
  });

  it("labels every platform class", () => {
    const classes: PlatformClass[] = ["UNKNOWN", "MULTIROTOR", "FIXED_WING"];
    for (const c of classes) expect(PLATFORM_LABEL[c]).toBeTruthy();
  });
});

describe("formatDuration", () => {
  it("shows an em dash rather than '0s' for no duration", () => {
    expect(formatDuration(0)).toBe("—");
  });

  it("shows bare seconds under a minute", () => {
    expect(formatDuration(5)).toBe("5s");
    expect(formatDuration(59)).toBe("59s");
  });

  it("zero-pads the seconds once minutes appear, so the field stops jumping", () => {
    expect(formatDuration(65)).toBe("1m 05s");
    expect(formatDuration(3600)).toBe("60m 00s");
  });

  it("rounds fractional seconds", () => {
    expect(formatDuration(9.6)).toBe("10s");
  });
});

describe("formatClock", () => {
  it("renders a unix timestamp as 24-hour wall time", () => {
    // Asserted by shape, not value: the result is local-timezone dependent.
    expect(formatClock(1_700_000_000)).toMatch(/^\d{2}:\d{2}:\d{2}$/);
  });
});

describe("basename", () => {
  it("keeps only the filename", () => {
    expect(basename("/var/videos/approach.mp4")).toBe("approach.mp4");
  });

  it("passes through a bare filename", () => {
    expect(basename("approach.mp4")).toBe("approach.mp4");
  });

  it("returns null for absent paths rather than an empty string", () => {
    expect(basename(null)).toBeNull();
    expect(basename(undefined)).toBeNull();
    expect(basename("")).toBeNull();
  });
});

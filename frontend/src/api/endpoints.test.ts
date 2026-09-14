import { describe, it, expect } from "vitest";
import { endpoints } from "./endpoints";

// These paths are the frontend's half of the API contract. The point of the
// module is that a backend rename breaks exactly one file — these assertions
// are what makes it break loudly instead of 404ing during a demo.
describe("endpoints", () => {
  it.each([
    ["health", endpoints.health(), "/api/health"],
    ["telemetry", endpoints.telemetry(), "/api/telemetry"],
    ["events", endpoints.events(), "/api/events"],
    ["authorize", endpoints.authorize(), "/api/authorize"],
    ["reset", endpoints.reset(), "/api/reset"],
    ["source", endpoints.source(), "/api/source"],
    ["selectVideo", endpoints.selectVideo(), "/api/source/video"],
    ["selectCamera", endpoints.selectCamera(), "/api/source/camera"],
    ["selectDetector", endpoints.selectDetector(), "/api/source/detector"],
    ["setThreshold", endpoints.setThreshold(), "/api/source/threshold"],
    ["upload", endpoints.upload(), "/api/source/upload"],
    ["videoStream", endpoints.videoStream(), "/api/video"],
  ])("%s resolves to %s", (_name, actual, expected) => {
    expect(actual).toBe(expected);
  });

  it("points the telemetry socket at the ws route", () => {
    expect(endpoints.telemetrySocket()).toMatch(/^wss?:\/\/.*\/ws\/telemetry$/);
  });

  it("percent-encodes upload names so spaces and slashes cannot escape the path", () => {
    expect(endpoints.deleteUpload("my clip.mp4")).toBe(
      "/api/source/upload/my%20clip.mp4",
    );
    expect(endpoints.deleteUpload("../../etc/passwd")).toBe(
      "/api/source/upload/..%2F..%2Fetc%2Fpasswd",
    );
  });
});

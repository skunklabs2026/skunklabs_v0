import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { API_BASE, apiUrl, wsUrl } from "./config";

describe("API_BASE", () => {
  it("is empty by default, so every URL is same-origin", () => {
    // VITE_API_BASE is unset under test; this is the deployment both the dev
    // proxy and the production single-origin build rely on.
    expect(API_BASE).toBe("");
  });
});

describe("apiUrl", () => {
  it("returns the path unchanged when same-origin", () => {
    expect(apiUrl("/api/health")).toBe("/api/health");
  });
});

describe("wsUrl", () => {
  const original = window.location.protocol;

  beforeEach(() => {
    Object.defineProperty(window, "location", {
      writable: true,
      value: { protocol: "http:", host: "127.0.0.1:8000" },
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      writable: true,
      value: { protocol: original, host: "localhost:3000" },
    });
  });

  it("uses ws: on an http page", () => {
    expect(wsUrl("/ws/telemetry")).toBe("ws://127.0.0.1:8000/ws/telemetry");
  });

  it("upgrades to wss: on an https page — a wss page cannot open a ws socket", () => {
    Object.defineProperty(window, "location", {
      writable: true,
      value: { protocol: "https:", host: "demo.example:8443" },
    });
    expect(wsUrl("/ws/telemetry")).toBe("wss://demo.example:8443/ws/telemetry");
  });
});

import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, describe, expect, it } from "vitest";
import { RouteLink } from "./RouteLink";
import { navigate, parseRoute, useRoute } from "./useRoute";

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

describe("routes", () => {
  it.each([
    ["/", "map"],
    ["/map", "map"],
    ["/map/", "map"],
    ["/launcher", "launcher"],
    ["/sensor-lab", "sensor-lab"],
    ["/unknown", "map"],
  ] as const)("parses %j as %s", (path, route) => {
    expect(parseRoute(path)).toBe(route);
  });

  it("settles / on /map", () => {
    const { result } = renderHook(() => useRoute());
    expect(result.current).toBe("map");
    expect(window.location.pathname).toBe("/map");
  });

  it("navigates without reloading and follows browser history", () => {
    const { result } = renderHook(() => useRoute());

    act(() => navigate("launcher"));
    expect(result.current).toBe("launcher");
    expect(window.location.pathname).toBe("/launcher");

    act(() => {
      window.history.replaceState(null, "", "/map");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(result.current).toBe("map");
  });

  it("does not push a duplicate history entry", () => {
    window.history.replaceState(null, "", "/launcher");
    const before = window.history.length;
    navigate("launcher");
    expect(window.history.length).toBe(before);
  });
});

describe("RouteLink", () => {
  it("navigates in place on a plain click", () => {
    render(createElement(RouteLink, { to: "launcher", children: "Launcher" }));
    const link = screen.getByRole("link", { name: "Launcher" });
    expect(link).toHaveAttribute("href", "/launcher");
    fireEvent.click(link);
    expect(window.location.pathname).toBe("/launcher");
  });

  it("leaves modified clicks to the browser", () => {
    render(createElement(RouteLink, { to: "launcher", children: "Launcher" }));
    fireEvent.click(screen.getByRole("link"), { metaKey: true });
    expect(window.location.pathname).toBe("/");
  });
});

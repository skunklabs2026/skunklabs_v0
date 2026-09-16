import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useLaunchCue, useAuthorizeHotkey } from "./useMissionCues";
import type { MissionState } from "../types";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("useLaunchCue", () => {
  it("does not fire for states other than AUTHORIZED", () => {
    const { result } = renderHook(() => useLaunchCue("TRACKING"));
    expect(result.current).toBe(false);
  });

  it("fires on entering AUTHORIZED and clears itself", () => {
    const { result, rerender } = renderHook(
      ({ state }: { state: MissionState }) => useLaunchCue(state),
      { initialProps: { state: "FOLLOWING" as MissionState } },
    );
    expect(result.current).toBe(false);

    rerender({ state: "AUTHORIZED" });
    expect(result.current).toBe(true);

    act(() => void vi.advanceTimersByTime(1599));
    expect(result.current).toBe(true);
    act(() => void vi.advanceTimersByTime(1));
    expect(result.current).toBe(false);
  });

  // The point of tracking the transition rather than the state: holding
  // AUTHORIZED must not hold the flash on screen.
  it("does not re-fire while AUTHORIZED is merely held", () => {
    const { result, rerender } = renderHook(
      ({ state }: { state: MissionState }) => useLaunchCue(state),
      { initialProps: { state: "AUTHORIZED" as MissionState } },
    );
    expect(result.current).toBe(true);
    act(() => void vi.advanceTimersByTime(1600));
    expect(result.current).toBe(false);

    rerender({ state: "AUTHORIZED" });
    expect(result.current).toBe(false);
  });

  it("fires again on re-entering AUTHORIZED after leaving it", () => {
    const { result, rerender } = renderHook(
      ({ state }: { state: MissionState }) => useLaunchCue(state),
      { initialProps: { state: "AUTHORIZED" as MissionState } },
    );
    act(() => void vi.advanceTimersByTime(1600));
    expect(result.current).toBe(false);

    rerender({ state: "SEARCHING" });
    rerender({ state: "AUTHORIZED" });
    expect(result.current).toBe(true);
  });
});

describe("useAuthorizeHotkey", () => {
  function press(
    code: string,
    init: Partial<KeyboardEventInit> = {},
    target?: Element,
  ) {
    const event = new KeyboardEvent("keydown", { code, cancelable: true, ...init });
    (target ?? window).dispatchEvent(event);
    return event;
  }

  it("authorizes on Space", () => {
    const onAuthorize = vi.fn();
    renderHook(() => useAuthorizeHotkey(true, onAuthorize));
    press("Space");
    expect(onAuthorize).toHaveBeenCalledTimes(1);
  });

  it("prevents the default so Space does not also scroll the page", () => {
    renderHook(() => useAuthorizeHotkey(true, vi.fn()));
    const event = press("Space");
    expect(event.defaultPrevented).toBe(true);
  });

  // The keyboard must not be a way around the authorization interlock.
  it("does nothing when disabled — the interlock is not bypassable", () => {
    const onAuthorize = vi.fn();
    renderHook(() => useAuthorizeHotkey(false, onAuthorize));
    press("Space");
    expect(onAuthorize).not.toHaveBeenCalled();
  });

  it("ignores keys other than Space", () => {
    const onAuthorize = vi.fn();
    renderHook(() => useAuthorizeHotkey(true, onAuthorize));
    press("Enter");
    press("KeyA");
    expect(onAuthorize).not.toHaveBeenCalled();
  });

  it("ignores auto-repeat, so holding Space authorizes once", () => {
    const onAuthorize = vi.fn();
    renderHook(() => useAuthorizeHotkey(true, onAuthorize));
    press("Space", { repeat: true });
    expect(onAuthorize).not.toHaveBeenCalled();
  });

  it.each(["INPUT", "TEXTAREA"])("ignores Space typed into a %s", (tag) => {
    const onAuthorize = vi.fn();
    renderHook(() => useAuthorizeHotkey(true, onAuthorize));
    const field = document.createElement(tag);
    document.body.appendChild(field);
    press("Space", {}, field);
    expect(onAuthorize).not.toHaveBeenCalled();
    field.remove();
  });

  it("ignores Space inside a contenteditable region", () => {
    const onAuthorize = vi.fn();
    renderHook(() => useAuthorizeHotkey(true, onAuthorize));
    const div = document.createElement("div");
    Object.defineProperty(div, "isContentEditable", { value: true });
    document.body.appendChild(div);
    press("Space", {}, div);
    expect(onAuthorize).not.toHaveBeenCalled();
    div.remove();
  });

  it("stops listening on unmount", () => {
    const onAuthorize = vi.fn();
    const { unmount } = renderHook(() => useAuthorizeHotkey(true, onAuthorize));
    unmount();
    press("Space");
    expect(onAuthorize).not.toHaveBeenCalled();
  });
});

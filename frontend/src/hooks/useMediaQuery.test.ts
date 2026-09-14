import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useMediaQuery, useCompactLayout, BREAKPOINTS } from "./useMediaQuery";

/** A matchMedia stand-in whose result can be flipped from a test. */
class FakeMediaQueryList {
  matches = false;
  private listeners = new Set<() => void>();
  constructor(public media: string) {}
  addEventListener(_: string, fn: () => void) {
    this.listeners.add(fn);
  }
  removeEventListener(_: string, fn: () => void) {
    this.listeners.delete(fn);
  }
  set(value: boolean, { notify = true } = {}) {
    this.matches = value;
    if (notify) this.listeners.forEach((fn) => fn());
  }
  get listenerCount() {
    return this.listeners.size;
  }
}

let lists: Map<string, FakeMediaQueryList>;

function listFor(query: string): FakeMediaQueryList {
  const list = lists.get(query);
  if (!list) throw new Error(`no list created for ${query}`);
  return list;
}

beforeEach(() => {
  lists = new Map();
  vi.stubGlobal("matchMedia", (query: string) => {
    const existing = lists.get(query);
    if (existing) return existing;
    const created = new FakeMediaQueryList(query);
    lists.set(query, created);
    return created;
  });
});

afterEach(() => vi.unstubAllGlobals());

describe("useMediaQuery", () => {
  it("is correct on the first paint, not after an effect", () => {
    // The initialiser reads the real value; a hook that started false and
    // corrected itself would flash the wrong layout.
    lists.set("(min-width: 100px)", new FakeMediaQueryList("(min-width: 100px)"));
    listFor("(min-width: 100px)").set(true, { notify: false });

    const { result } = renderHook(() => useMediaQuery("(min-width: 100px)"));
    expect(result.current).toBe(true);
  });

  it("updates when the media query changes", () => {
    const { result } = renderHook(() => useMediaQuery(BREAKPOINTS.compact));
    expect(result.current).toBe(false);

    act(() => listFor(BREAKPOINTS.compact).set(true));
    expect(result.current).toBe(true);

    act(() => listFor(BREAKPOINTS.compact).set(false));
    expect(result.current).toBe(false);
  });

  // The resize listener exists because some embedded viewports resize without
  // ever dispatching a media-query change event.
  it("also recomputes on window resize, for viewports that never fire change", () => {
    const { result } = renderHook(() => useMediaQuery(BREAKPOINTS.compact));

    act(() => listFor(BREAKPOINTS.compact).set(true, { notify: false }));
    expect(result.current).toBe(false); // no event fired yet

    act(() => window.dispatchEvent(new Event("resize")));
    expect(result.current).toBe(true);
  });

  it("removes both listeners on unmount", () => {
    const { unmount } = renderHook(() => useMediaQuery(BREAKPOINTS.compact));
    const removeWindow = vi.spyOn(window, "removeEventListener");

    expect(listFor(BREAKPOINTS.compact).listenerCount).toBe(1);
    unmount();
    expect(listFor(BREAKPOINTS.compact).listenerCount).toBe(0);
    expect(removeWindow).toHaveBeenCalledWith("resize", expect.any(Function));
    removeWindow.mockRestore();
  });

  it("re-subscribes when the query itself changes", () => {
    const { rerender, result } = renderHook(({ q }) => useMediaQuery(q), {
      initialProps: { q: "(max-width: 100px)" },
    });
    expect(listFor("(max-width: 100px)").listenerCount).toBe(1);

    rerender({ q: "(max-width: 200px)" });
    expect(listFor("(max-width: 100px)").listenerCount).toBe(0);
    expect(listFor("(max-width: 200px)").listenerCount).toBe(1);

    act(() => listFor("(max-width: 200px)").set(true));
    expect(result.current).toBe(true);
  });
});

describe("BREAKPOINTS", () => {
  it("names the pixel value once so components never repeat it", () => {
    expect(BREAKPOINTS.compact).toBe("(max-width: 900px)");
    expect(BREAKPOINTS.touch).toBe("(pointer: coarse)");
  });
});

describe("useCompactLayout", () => {
  it("is useMediaQuery bound to the compact breakpoint", () => {
    const { result } = renderHook(() => useCompactLayout());
    expect(result.current).toBe(false);
    act(() => listFor(BREAKPOINTS.compact).set(true));
    expect(result.current).toBe(true);
  });
});

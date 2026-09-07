import { useEffect, useState } from "react";

/**
 * Track a CSS media query from React.
 *
 * Used where a layout change is structural rather than cosmetic — on a phone
 * the side panel becomes tabs, which is a different component tree, not a
 * different stylesheet. Anything achievable in CSS alone should stay in CSS.
 */
export function useMediaQuery(query: string): boolean {
  // Initialised from the real value so the first paint is already correct;
  // guarded for any non-browser render.
  const [matches, setMatches] = useState(() =>
    typeof window === "undefined" ? false : window.matchMedia(query).matches,
  );

  useEffect(() => {
    const list = window.matchMedia(query);
    // Read from the list, never from a captured value, so both listeners
    // always observe the current result.
    const update = () => setMatches(list.matches);

    update();
    list.addEventListener("change", update);
    // `resize` is a deliberate belt-and-braces fallback. Some embedded and
    // remote-viewport environments resize the page without ever dispatching
    // the media-query change event, which strands the layout in whichever
    // mode it started in. `update` is idempotent and React bails out of a
    // set to the same value, so the extra listener costs a boolean compare.
    window.addEventListener("resize", update);

    return () => {
      list.removeEventListener("change", update);
      window.removeEventListener("resize", update);
    };
  }, [query]);

  return matches;
}

/** Breakpoints, named once so components never repeat a pixel value. */
export const BREAKPOINTS = {
  /** Below this the side panel stacks under the video and becomes tabbed. */
  compact: "(max-width: 900px)",
  /** Coarse pointer — touch targets need to be bigger. */
  touch: "(pointer: coarse)",
} as const;

export const useCompactLayout = () => useMediaQuery(BREAKPOINTS.compact);

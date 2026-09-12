import { useEffect, useRef, useState } from "react";
import type { MissionState } from "../types";

/** How long the launch flash stays on screen. */
const LAUNCH_CUE_MS = 1600;

/**
 * True for a moment after the mission enters AUTHORIZED.
 *
 * Fires on the *transition*, not the state, so holding AUTHORIZED does not
 * hold the flash - and re-entering it later plays the cue again.
 */
export function useLaunchCue(state: MissionState): boolean {
  const [launching, setLaunching] = useState(false);
  const previous = useRef<MissionState | null>(null);

  useEffect(() => {
    const entered = previous.current !== "AUTHORIZED" && state === "AUTHORIZED";
    previous.current = state;
    if (!entered) return;

    setLaunching(true);
    const timer = window.setTimeout(() => setLaunching(false), LAUNCH_CUE_MS);
    return () => window.clearTimeout(timer);
  }, [state]);

  return launching;
}

/**
 * Space bar authorizes, so the demo can be driven without the mouse.
 *
 * Gated by `enabled` exactly like the on-screen button - the keyboard must
 * not be a way around the authorization interlock. Ignored while the
 * operator is typing in a field.
 */
export function useAuthorizeHotkey(
  enabled: boolean,
  onAuthorize: () => void,
): void {
  useEffect(() => {
    if (!enabled) return;

    const onKey = (event: KeyboardEvent) => {
      if (event.code !== "Space" || event.repeat) return;

      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) {
        return;
      }

      event.preventDefault();
      onAuthorize();
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled, onAuthorize]);
}

import { useCallback, useState } from "react";

export type ViewMode = "SENSOR" | "TACTICAL";

const STORAGE_KEY = "skunklabs.viewMode";

/**
 * Which primary visualisation the operator is looking at.
 *
 * Remembered across reloads, because an operator who has chosen the tactical
 * view should not have to choose it again after a refresh mid-demo. Storage
 * is wrapped: a private window or blocked site data throws on access, and a
 * console that will not render because it could not read a preference is a
 * far worse failure than forgetting one.
 */
function readStored(): ViewMode {
  try {
    return localStorage.getItem(STORAGE_KEY) === "TACTICAL" ? "TACTICAL" : "SENSOR";
  } catch {
    return "SENSOR";
  }
}

export function useViewMode(): [ViewMode, (mode: ViewMode) => void] {
  const [mode, setMode] = useState<ViewMode>(readStored);

  const select = useCallback((next: ViewMode) => {
    setMode(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Preference is per-browser convenience only; losing it costs nothing.
    }
  }, []);

  return [mode, select];
}

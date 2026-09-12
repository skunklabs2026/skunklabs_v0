import type { Tone } from "../../scenario/format";

/** The class that sets `--tone` for a status colour family (see console.css). */
export function toneClass(tone: Tone): string {
  return `c-tone-${tone}`;
}

/** Status colour primitives: an LED, a pill, and pills for node and mission state. */

import type { MissionState, NodeState } from "../../scenario/contract";
import {
  MISSION_LABEL,
  MISSION_TONE,
  NODE_LABEL,
  NODE_TONE,
  type Tone,
} from "../../scenario/format";
import { toneClass } from "./toneClass";

export function Led({ tone }: { tone: Tone }) {
  return <span className={`c-led ${toneClass(tone)}`} aria-hidden="true" />;
}

export function Pill({
  tone,
  label,
  live = false,
  large = false,
}: {
  tone: Tone;
  label: string;
  /** Something is in motion: the LED pulses. */
  live?: boolean;
  large?: boolean;
}) {
  const classes = [
    "c-pill",
    toneClass(tone),
    large ? "is-large" : "",
    live ? "is-live" : "",
  ];
  return (
    <span className={classes.filter(Boolean).join(" ")}>
      <Led tone={tone} />
      {label}
    </span>
  );
}

const MOVING: ReadonlySet<NodeState> = new Set([
  "TRACK_RECEIVED",
  "ORIENTING",
  "AUTHORIZED",
  "SIMULATED_LAUNCH",
]);

export function NodeStatePill({
  state,
  large = false,
}: {
  state: NodeState;
  large?: boolean;
}) {
  return (
    <Pill
      tone={NODE_TONE[state]}
      label={NODE_LABEL[state]}
      live={MOVING.has(state)}
      large={large}
    />
  );
}

export function MissionPill({ state }: { state: MissionState }) {
  return (
    <Pill
      tone={MISSION_TONE[state]}
      label={MISSION_LABEL[state]}
      live={state === "RUNNING"}
    />
  );
}

import { useMemo } from "react";
import { ErrorBoundary } from "../components/common/ErrorBoundary";
import { MissionTimeline } from "../components/operator/MissionTimeline";
import { SidePanel } from "../components/operator/SidePanel";
import { StateBanner } from "../components/operator/StateBanner";
import { TacticalView } from "../components/operator/TacticalView";
import { VideoStage } from "../components/operator/VideoStage";
import { useCompactLayout } from "../hooks/useMediaQuery";
import { useAuthorizeHotkey, useLaunchCue } from "../hooks/useMissionCues";
import { useViewMode } from "../hooks/useViewMode";
import type { MissionEvent, MissionState, TelemetryFrame } from "../types";

interface Props {
  telemetry: TelemetryFrame | null;
  events: MissionEvent[];
  connected: boolean;
  onAuthorize: () => void;
  onReset: () => void;
  onChangeSource: () => void;
}

/**
 * The live mission console.
 *
 * Reads top to bottom as one operational story: which canister this is and
 * whether it is healthy, how far the mission has got, what it is looking at,
 * and what the operator is being asked to decide.
 *
 * Layout and wiring only - the launch cue and the keyboard shortcut live in
 * `useMissionCues`, the readouts in `SidePanel`, the sequence in
 * `MissionTimeline`. Adding a panel here should never mean editing mission
 * behaviour.
 */
export function OperatorScreen({
  telemetry,
  events,
  connected,
  onAuthorize,
  onReset,
  onChangeSource,
}: Props) {
  const compact = useCompactLayout();
  const [view, setView] = useViewMode();

  const mission = telemetry?.mission ?? null;
  const system = telemetry?.system ?? null;
  const canister = telemetry?.canister ?? null;
  const state: MissionState = mission?.state ?? "SEARCHING";

  const targets = useMemo(() => telemetry?.targets ?? [], [telemetry]);
  const primary = useMemo(
    () => targets.find((target) => target.is_primary) ?? null,
    [targets],
  );

  const launching = useLaunchCue(state);
  useAuthorizeHotkey(Boolean(mission?.can_authorize), onAuthorize);

  // The headline comes from the canister's own roll-up, so the badge and the
  // subsystem list can never disagree about whether the unit is operational.
  const canisterState = canister?.state ?? "INITIALISING";
  const healthy = canisterState === "OPERATIONAL";

  return (
    <div className="shell">
      <header className="topbar is-canister">
        <div className="identity">
          <span className="wordmark">SkunkLabs</span>
          <span className="canister-id">
            {canister?.canister_id ?? "Canister 01"}
          </span>
        </div>

        <div className="topbar-right">
          <div className="dot-row" title={canister?.detail}>
            <span
              className={`dot ${connected && healthy ? "is-ok" : connected ? "is-unknown" : "is-bad"}`}
            />
            <span className="link-state">
              {connected ? canisterState : "LINK LOST"}
            </span>
          </div>
          <span className="link-badge">LOCAL</span>
          <button
            type="button"
            className="link-button"
            onClick={onChangeSource}
            title="Canister setup - source and perception settings"
          >
            Setup ▸
          </button>
        </div>
      </header>

      <ErrorBoundary label="Mission sequence">
        <MissionTimeline mission={mission} />
      </ErrorBoundary>

      <main className="main">
        <section className="stage">
          <div className="view-switch" role="tablist" aria-label="View mode">
            {(["SENSOR", "TACTICAL"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                role="tab"
                aria-selected={view === mode}
                className={`view-tab${view === mode ? " is-active" : ""}`}
                onClick={() => setView(mode)}
              >
                {mode}
              </button>
            ))}
          </div>

          <ErrorBoundary label="Sensor view">
            {view === "SENSOR" ? (
              <VideoStage
                system={system}
                targets={targets}
                state={state}
                intercept={telemetry?.intercept ?? null}
                interceptor={telemetry?.interceptor ?? null}
                launching={launching}
                hasTelemetry={telemetry !== null}
              />
            ) : (
              <div className="viewport">
                <TacticalView
                  tactical={telemetry?.tactical ?? null}
                  state={state}
                />
              </div>
            )}
          </ErrorBoundary>

          <StateBanner
            state={state}
            mission={mission}
            readiness={telemetry?.readiness ?? null}
            onAuthorize={onAuthorize}
          />
        </section>

        <SidePanel
          system={system}
          canister={canister}
          readiness={telemetry?.readiness ?? null}
          launcher={telemetry?.launcher ?? null}
          primary={primary}
          state={state}
          events={events}
          connected={connected}
          compact={compact}
          onReset={onReset}
          onChangeSource={onChangeSource}
        />
      </main>
    </div>
  );
}

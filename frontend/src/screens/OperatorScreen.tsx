import { useMemo } from "react";
import { ErrorBoundary } from "../components/common/ErrorBoundary";
import { SidePanel } from "../components/operator/SidePanel";
import { StateBanner } from "../components/operator/StateBanner";
import { VideoStage } from "../components/operator/VideoStage";
import { useCompactLayout } from "../hooks/useMediaQuery";
import { useAuthorizeHotkey, useLaunchCue } from "../hooks/useMissionCues";
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
 * Layout and wiring only — the launch cue and the keyboard shortcut live in
 * `useMissionCues`, the readouts in `SidePanel`. Adding a panel here should
 * never mean editing mission behaviour.
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

  const mission = telemetry?.mission ?? null;
  const system = telemetry?.system ?? null;
  const state: MissionState = mission?.state ?? "SEARCHING";

  const targets = useMemo(() => telemetry?.targets ?? [], [telemetry]);
  const primary = useMemo(
    () => targets.find((target) => target.is_primary) ?? null,
    [targets],
  );

  const launching = useLaunchCue(state);
  useAuthorizeHotkey(Boolean(mission?.can_authorize), onAuthorize);

  const sensorOnline = Boolean(system?.sensor_online);

  return (
    <div className="shell">
      <header className="topbar">
        <span className="wordmark">SkunkLabs</span>
        <span className="canister">Canister 01</span>
        <div className="topbar-right">
          <button
            type="button"
            className="link-button"
            onClick={onChangeSource}
            title="Load different footage"
          >
            {system ? `${system.video_source} · ${system.detector}` : "source"} ▸
          </button>
          <div className="dot-row">
            <span
              className={`dot ${connected && sensorOnline ? "is-ok" : "is-bad"}`}
            />
            <span className="link-state">
              {connected ? "System Online" : "Reconnecting"}
            </span>
          </div>
        </div>
      </header>

      <main className="main">
        <section className="stage">
          <ErrorBoundary label="Sensor view">
            <VideoStage
              system={system}
              targets={targets}
              state={state}
              intercept={telemetry?.intercept ?? null}
              interceptor={telemetry?.interceptor ?? null}
              launching={launching}
              hasTelemetry={telemetry !== null}
            />
          </ErrorBoundary>
          <StateBanner state={state} mission={mission} onAuthorize={onAuthorize} />
        </section>

        <SidePanel
          system={system}
          mission={mission}
          primary={primary}
          events={events}
          connected={connected}
          intercept={telemetry?.intercept ?? null}
          interceptor={telemetry?.interceptor ?? null}
          compact={compact}
          onReset={onReset}
          onChangeSource={onChangeSource}
        />
      </main>
    </div>
  );
}

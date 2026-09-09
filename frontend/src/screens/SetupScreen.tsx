import { useEffect, useState } from "react";
import { endpoints } from "../api";
import { AdvancedPanel } from "../components/setup/AdvancedPanel";
import { Dropzone } from "../components/setup/Dropzone";
import { VerifyPanel } from "../components/setup/VerifyPanel";
import { VideoLibrary } from "../components/setup/VideoLibrary";
import { StatusDot } from "../components/common/Readout";
import { UNKNOWN_SUBSYSTEM_STATES } from "../format";
import { basename } from "../format";
import { useSource } from "../hooks/useSource";
import type { Subsystem, TelemetryFrame } from "../types";

interface Props {
  telemetry: TelemetryFrame | null;
  connected: boolean;
  onBegin: () => void;
}

/** Subsystems worth confirming before a run. */
const PREFLIGHT: readonly string[] = [
  "SENSOR",
  "PERCEPTION",
  "TRACKER",
  "COMPUTE",
  "LAUNCHER",
];

/**
 * Canister setup — the screen the operator lands on.
 *
 * Framed as bringing a canister online rather than configuring a model. Two
 * steps: give the canister a sensor feed, then confirm the canister reports
 * itself ready. Perception settings are one disclosure away, because they are
 * how the canister sees, not what it does.
 *
 * BEGIN MISSION stays disabled until frames are genuinely flowing, so nobody
 * starts a mission against a dead sensor.
 */
export function SetupScreen({ telemetry, connected, onBegin }: Props) {
  const {
    status,
    busy,
    message,
    error,
    uploadPercent,
    selectVideo,
    selectDetector,
    setThreshold,
    selectCamera,
    upload,
    removeUpload,
  } = useSource();

  // Mirrored locally so the slider stays responsive while the POST is in
  // flight. Cleared whenever the detector changes, since each carries its own
  // threshold and the backend value should win.
  const [thresholdLocal, setThresholdLocal] = useState<number | null>(null);

  const system = telemetry?.system ?? null;
  const detection = telemetry?.detection ?? null;
  const canister = telemetry?.canister ?? null;
  const live = Boolean(system?.sensor_online && (system?.frame_index ?? 0) > 0);

  // Telemetry is authoritative about what is actually running; the source
  // status can lag by a frame while a swap is applied on the worker thread.
  const detector = system?.detector ?? status?.detector ?? "motion";
  const threshold = thresholdLocal ?? status?.detection_threshold ?? 0.5;

  useEffect(() => {
    setThresholdLocal(null);
  }, [status?.detector]);

  const sourceName =
    status?.video_source === "camera"
      ? `Camera ${status.camera_index}`
      : basename(status?.active_video);

  const frameWidth = system?.frame_width || 16;
  const frameHeight = system?.frame_height || 9;

  const preflight: Subsystem[] = (canister?.subsystems ?? []).filter((s) =>
    PREFLIGHT.includes(s.id),
  );

  return (
    <div className="setup">
      <header className="topbar is-canister">
        <div className="identity">
          <span className="wordmark">SkunkLabs</span>
          <span className="canister-id">
            {canister?.canister_id ?? "Canister 01"}
          </span>
        </div>
        <span className="setup-mode">Canister Setup</span>
        <div className="topbar-right">
          <div className="dot-row">
            <span className={`dot ${connected ? "is-ok" : "is-bad"}`} />
            <span className="link-state">
              {connected ? (canister?.state ?? "ONLINE") : "CONNECTING"}
            </span>
          </div>
          <span className="link-badge">LOCAL</span>
        </div>
      </header>

      <div className="setup-body">
        {/* ---- 1. sensor feed ---- */}
        <section className="setup-col">
          <h2 className="setup-step">
            <span className="step-num">1</span> Sensor feed
          </h2>
          <p className="setup-hint">
            What CANISTER 01 is looking at. Load recorded footage, or attach the
            live camera on this machine.
          </p>

          <Dropzone
            onFile={(file) => void upload(file)}
            percent={uploadPercent}
            disabled={busy}
          />

          <div className="setup-subhead">
            <span>Library</span>
            <button
              type="button"
              className="link-button"
              disabled={busy}
              onClick={() => void selectCamera(0)}
            >
              Attach live camera
            </button>
          </div>

          <VideoLibrary
            videos={status?.videos ?? []}
            busy={busy}
            loaded={status !== null}
            onSelect={(video) => void selectVideo(video)}
            onRemove={(name) => void removeUpload(name)}
          />

          <AdvancedPanel
            available={status?.detectors_available ?? ["motion", "yolo"]}
            active={detector}
            threshold={threshold}
            busy={busy}
            onSelect={(name) => void selectDetector(name)}
            onThreshold={(value) => {
              setThresholdLocal(value);
              void setThreshold(value);
            }}
          />
        </section>

        {/* ---- 2. canister readiness ---- */}
        <section className="setup-col">
          <h2 className="setup-step">
            <span className="step-num">2</span> Confirm canister ready
          </h2>
          <p className="setup-hint">
            The canister reports on itself. Every subsystem below must be reporting
            before a mission begins.
          </p>

          <div className="preflight">
            {preflight.map((subsystem) => {
              const tone = UNKNOWN_SUBSYSTEM_STATES.has(subsystem.state)
                ? "unknown"
                : subsystem.nominal
                  ? "ok"
                  : "bad";
              return (
                <div
                  key={subsystem.id}
                  className={`subsystem is-${tone}`}
                  title={subsystem.detail}
                >
                  <StatusDot tone={tone} />
                  <span className="subsystem-name">{subsystem.label}</span>
                  <span className="subsystem-state">{subsystem.state}</span>
                </div>
              );
            })}
            {preflight.length === 0 && (
              <div className="note">Waiting for canister telemetry…</div>
            )}
          </div>

          <div className="preview">
            {live ? (
              <div
                className="preview-frame"
                style={{ aspectRatio: `${frameWidth} / ${frameHeight}` }}
              >
                <img
                  className="preview-feed"
                  src={endpoints.videoStream()}
                  alt="Sensor preview"
                />
              </div>
            ) : (
              <div className="preview-empty">
                {connected ? "Waiting for sensor…" : "Canister offline"}
              </div>
            )}
          </div>

          <VerifyPanel
            system={system}
            detection={detection}
            sourceName={sourceName}
            live={live}
          />

          {message && <div className="note is-ok">{message}</div>}
          {error && <div className="note is-bad">{error}</div>}

          <button
            type="button"
            className="begin-button"
            disabled={!live}
            onClick={onBegin}
          >
            {live ? "Begin mission" : "Attach a sensor feed to continue"}
          </button>
        </section>
      </div>
    </div>
  );
}

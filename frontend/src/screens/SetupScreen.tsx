import { useEffect, useState } from "react";
import { endpoints } from "../api";
import { DetectorChoice } from "../components/setup/DetectorChoice";
import { Dropzone } from "../components/setup/Dropzone";
import { VerifyPanel } from "../components/setup/VerifyPanel";
import { VideoLibrary } from "../components/setup/VideoLibrary";
import { basename } from "../format";
import { useSource } from "../hooks/useSource";
import type { TelemetryFrame } from "../types";

interface Props {
  telemetry: TelemetryFrame | null;
  connected: boolean;
  onBegin: () => void;
}

/**
 * Mission setup — the screen the operator lands on.
 *
 * Three steps, in the order the work actually happens: load footage, pick a
 * detector, then confirm the system is seeing something before committing to
 * a run. BEGIN MISSION stays disabled until frames are genuinely flowing, so
 * nobody starts a mission against a dead source.
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

  return (
    <div className="setup">
      <header className="topbar">
        <span className="wordmark">SkunkLabs</span>
        <span className="canister">Canister 01 · Mission Setup</span>
        <div className="topbar-right">
          <div className="dot-row">
            <span className={`dot ${connected ? "is-ok" : "is-bad"}`} />
            <span>{connected ? "Backend online" : "Connecting"}</span>
          </div>
        </div>
      </header>

      <div className="setup-body">
        {/* ---- 1. source ---- */}
        <section className="setup-col">
          <h2 className="setup-step">
            <span className="step-num">1</span> Load footage
          </h2>

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
              Use camera instead
            </button>
          </div>

          <VideoLibrary
            videos={status?.videos ?? []}
            busy={busy}
            loaded={status !== null}
            onSelect={(video) => void selectVideo(video)}
            onRemove={(name) => void removeUpload(name)}
          />
        </section>

        {/* ---- 2. detector, 3. verify ---- */}
        <section className="setup-col">
          <h2 className="setup-step">
            <span className="step-num">2</span> Choose a detector
          </h2>

          <DetectorChoice
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

          <h2 className="setup-step">
            <span className="step-num">3</span> Confirm it is tracking
          </h2>

          <div className="preview">
            {live ? (
              <div
                className="preview-frame"
                style={{ aspectRatio: `${frameWidth} / ${frameHeight}` }}
              >
                <img
                  className="preview-feed"
                  src={endpoints.videoStream()}
                  alt="Source preview"
                />
              </div>
            ) : (
              <div className="preview-empty">
                {connected ? "Waiting for frames…" : "Backend offline"}
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
            {live ? "Begin mission" : "Load a source to continue"}
          </button>
        </section>
      </div>
    </div>
  );
}

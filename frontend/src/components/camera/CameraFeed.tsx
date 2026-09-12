import { useEffect, useState } from "react";
import { get } from "../../api/client";
import { endpoints } from "../../api/endpoints";
import { SimulatedCameraView } from "./SimulatedCameraView";

/** True when the backend is running the video pipeline and can stream frames. */
function useVideoAvailable(): boolean {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    let cancelled = false;
    get<{ video_pipeline?: boolean }>(endpoints.health())
      .then((health) => {
        if (!cancelled) setAvailable(Boolean(health.video_pipeline));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return available;
}

/**
 * A node's local sensor. The real camera stream from the video pipeline when
 * the backend runs one (SKUNK_VIDEO_PIPELINE_ENABLED=true), otherwise a
 * simulated view that turns with the node. Local awareness only - the mission
 * never reads from it.
 */
export function CameraFeed({ nodeId }: { nodeId: string | null }) {
  const videoAvailable = useVideoAvailable();
  const [preferVideo, setPreferVideo] = useState(true);
  const showVideo = videoAvailable && preferVideo;

  return (
    <section className="c-camera" aria-label="Local sensor">
      <div className="c-camera-head">
        <h2 className="c-panel-title">Local sensor · {nodeId ?? "-"} EO camera</h2>
        <div className="c-seg" role="group" aria-label="Camera source">
          <button
            type="button"
            aria-pressed={showVideo}
            disabled={!videoAvailable}
            title={
              videoAvailable
                ? "Camera stream from the video pipeline"
                : "Start the backend with SKUNK_VIDEO_PIPELINE_ENABLED=true"
            }
            onClick={() => setPreferVideo(true)}
          >
            Video
          </button>
          <button
            type="button"
            aria-pressed={!showVideo}
            onClick={() => setPreferVideo(false)}
          >
            Simulated
          </button>
        </div>
      </div>
      <div className="c-camera-frame">
        {showVideo ? (
          <img
            className="c-camera-video"
            src={endpoints.videoStream()}
            alt="Node camera stream"
          />
        ) : (
          <SimulatedCameraView nodeId={nodeId} />
        )}
        <span className="c-chip c-camera-tag">
          {showVideo ? "Live · video pipeline" : "Simulated feed"}
        </span>
      </div>
    </section>
  );
}

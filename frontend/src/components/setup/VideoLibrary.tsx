import { formatDuration } from "../../format";
import type { VideoInfo } from "../../types";

interface Props {
  videos: VideoInfo[];
  busy: boolean;
  onSelect: (video: VideoInfo) => void;
  onRemove: (name: string) => void;
  loaded: boolean;
}

/** The list of clips available on this machine. */
export function VideoLibrary({ videos, busy, onSelect, onRemove, loaded }: Props) {
  if (loaded && videos.length === 0) {
    return <div className="note">No clips yet. Drop one above to get started.</div>;
  }

  return (
    <div className="video-list">
      {videos.map((video) => (
        <div
          key={video.path}
          className={`video-item${video.is_active ? " is-active" : ""}`}
        >
          <button
            type="button"
            className="video-pick"
            disabled={busy}
            onClick={() => onSelect(video)}
            title={video.path}
          >
            <span className="video-name">{video.name}</span>
            <span className="video-meta">
              {video.width > 0 ? `${video.width}×${video.height}` : "?"} ·{" "}
              {formatDuration(video.duration)} · {video.size_mb} MB
              {video.uploaded ? " · uploaded" : ""}
            </span>
          </button>

          {/* Only uploads can be deleted, and never the one in use. */}
          {video.uploaded && !video.is_active && (
            <button
              type="button"
              className="video-remove"
              disabled={busy}
              title={`Delete ${video.name}`}
              aria-label={`Delete ${video.name}`}
              onClick={() => onRemove(video.name)}
            >
              ×
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

import { useRef, useState } from "react";
import { Meter } from "../common/Readout";

interface Props {
  onFile: (file: File) => void;
  percent: number | null;
  disabled?: boolean;
}

/** Drag-and-drop / click-to-browse target for loading a local video. */
export function Dropzone({ onFile, percent, disabled = false }: Props) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const take = (files: FileList | null) => {
    const file = files?.[0];
    if (file) onFile(file);
  };

  const browse = () => {
    if (!disabled) inputRef.current?.click();
  };

  return (
    <>
      <div
        className={`dropzone${dragging ? " is-dragging" : ""}`}
        role="button"
        tabIndex={0}
        aria-label="Upload a video"
        onClick={browse}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            browse();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          take(event.dataTransfer.files);
        }}
      >
        <div className="dropzone-title">Drop a video here</div>
        <div className="dropzone-sub">
          or click to browse · MP4, MOV, M4V, AVI, MKV, WEBM
        </div>
        {percent !== null && (
          <div className="dropzone-progress">
            <Meter value={percent / 100} />
            <span>{percent}%</span>
          </div>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept="video/*"
        hidden
        onChange={(event) => {
          take(event.target.files);
          // Reset so selecting the same file twice still fires onChange.
          event.target.value = "";
        }}
      />
    </>
  );
}

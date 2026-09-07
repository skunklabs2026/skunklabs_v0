/** Input selection: library, camera, detector, uploads. */

import type { CommandResponse, SourceStatus, VideoInfo } from "../types";
import { ApiError, del, get, post } from "./client";
import { endpoints } from "./endpoints";

export function fetchStatus(): Promise<SourceStatus> {
  return get<SourceStatus>(endpoints.source());
}

export function selectVideo(video: VideoInfo | string): Promise<CommandResponse> {
  return post<CommandResponse>(endpoints.selectVideo(), {
    path: typeof video === "string" ? video : video.path,
  });
}

export function selectCamera(index = 0): Promise<CommandResponse> {
  return post<CommandResponse>(endpoints.selectCamera(), { camera_index: index });
}

export function selectDetector(detector: string): Promise<CommandResponse> {
  return post<CommandResponse>(endpoints.selectDetector(), { detector });
}

export function setThreshold(threshold: number): Promise<CommandResponse> {
  return post<CommandResponse>(endpoints.setThreshold(), { threshold });
}

export function removeUpload(name: string): Promise<CommandResponse> {
  return del<CommandResponse>(endpoints.deleteUpload(name));
}

/** Progress as a whole percent, or null once the upload has finished. */
export type UploadProgress = (percent: number) => void;

/**
 * Upload a clip, reporting progress.
 *
 * XMLHttpRequest rather than fetch purely for `upload.onprogress`: a
 * multi-hundred-megabyte clip with no progress feedback is indistinguishable
 * from a hang, and `fetch` still cannot report request-body progress.
 */
export function uploadVideo(
  file: File,
  onProgress?: UploadProgress,
): Promise<CommandResponse> {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    form.append("file", file);

    const request = new XMLHttpRequest();
    request.open("POST", endpoints.upload());

    request.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    request.onload = () => {
      let body: { detail?: string } = {};
      try {
        body = JSON.parse(request.responseText);
      } catch {
        /* fall through to the status-code message */
      }
      if (request.status >= 200 && request.status < 300) {
        resolve(body as CommandResponse);
      } else {
        reject(
          new ApiError(
            body.detail ?? `Upload failed (${request.status})`,
            request.status,
          ),
        );
      }
    };

    request.onerror = () =>
      reject(new ApiError("Upload failed — is the backend running?", 0));
    request.onabort = () => reject(new ApiError("Upload cancelled.", 0));

    request.send(form);
  });
}

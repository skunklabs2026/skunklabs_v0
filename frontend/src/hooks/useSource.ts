import { useCallback, useEffect, useRef, useState } from "react";
import { sourceApi } from "../api";
import type { CommandResponse, SourceStatus, VideoInfo } from "../types";

/**
 * Input selection: the library, uploads, and detector choice.
 *
 * Owns the *state* of choosing a source — what is selected, whether a change
 * is in flight, what the backend said. The requests themselves live in
 * `api/source.ts`; this hook never builds a URL.
 *
 * Source and detector swaps are applied by the pipeline's worker thread
 * between frames, so a refresh issued immediately after a POST can still read
 * the previous value. Every mutation therefore schedules a second refresh.
 */

/** How long to wait before re-reading state the worker thread applies late. */
const SETTLE_DELAY_MS = 1200;

export interface SourceControls {
  status: SourceStatus | null;
  busy: boolean;
  message: string | null;
  error: string | null;
  uploadPercent: number | null;
  refresh: () => Promise<void>;
  selectVideo: (video: VideoInfo | string) => Promise<boolean>;
  selectDetector: (detector: string) => Promise<boolean>;
  setThreshold: (value: number) => Promise<boolean>;
  selectCamera: (index?: number) => Promise<boolean>;
  upload: (file: File) => Promise<boolean>;
  removeUpload: (name: string) => Promise<boolean>;
}

export function useSource(): SourceControls {
  const [status, setStatus] = useState<SourceStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploadPercent, setUploadPercent] = useState<number | null>(null);

  // Guards every setState against a component that unmounted mid-request —
  // the operator can leave the setup screen while an upload is still running.
  const alive = useRef(true);
  const settleTimer = useRef<number | null>(null);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      if (settleTimer.current !== null) window.clearTimeout(settleTimer.current);
    };
  }, []);

  const refresh = useCallback(async () => {
    try {
      const next = await sourceApi.fetchStatus();
      if (alive.current) setStatus(next);
    } catch {
      /* the telemetry link already surfaces connectivity problems */
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  /** Refresh now, then again once the worker thread has applied the change. */
  const refreshAndSettle = useCallback(async () => {
    await refresh();
    if (settleTimer.current !== null) window.clearTimeout(settleTimer.current);
    settleTimer.current = window.setTimeout(() => void refresh(), SETTLE_DELAY_MS);
  }, [refresh]);

  /**
   * Run one mutation with the shared busy/message/error handling.
   *
   * Every command in this hook succeeds or fails the same way, so the
   * bookkeeping lives here once rather than in each of the six callers.
   */
  const run = useCallback(
    async (action: () => Promise<CommandResponse>, fallback: string) => {
      setBusy(true);
      setError(null);
      setMessage(null);
      try {
        const response = await action();
        if (alive.current) setMessage(response.detail ?? fallback);
        await refreshAndSettle();
        return true;
      } catch (exc) {
        if (alive.current) {
          setError(exc instanceof Error ? exc.message : String(exc));
        }
        return false;
      } finally {
        if (alive.current) setBusy(false);
      }
    },
    [refreshAndSettle],
  );

  const selectVideo = useCallback(
    (video: VideoInfo | string) =>
      run(() => sourceApi.selectVideo(video), "Source loaded."),
    [run],
  );

  const selectDetector = useCallback(
    (detector: string) =>
      run(() => sourceApi.selectDetector(detector), "Detector changed."),
    [run],
  );

  const setThreshold = useCallback(
    (value: number) =>
      run(() => sourceApi.setThreshold(value), "Threshold updated."),
    [run],
  );

  const selectCamera = useCallback(
    (index = 0) => run(() => sourceApi.selectCamera(index), "Camera selected."),
    [run],
  );

  const removeUpload = useCallback(
    (name: string) => run(() => sourceApi.removeUpload(name), "Deleted."),
    [run],
  );

  const upload = useCallback(
    async (file: File) => {
      setUploadPercent(0);
      const ok = await run(
        () =>
          sourceApi.uploadVideo(file, (percent) => {
            if (alive.current) setUploadPercent(percent);
          }),
        "Uploaded.",
      );
      if (alive.current) setUploadPercent(null);
      return ok;
    },
    [run],
  );

  return {
    status,
    busy,
    message,
    error,
    uploadPercent,
    refresh,
    selectVideo,
    selectDetector,
    setThreshold,
    selectCamera,
    upload,
    removeUpload,
  };
}

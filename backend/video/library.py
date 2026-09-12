"""Local video library.

Discovers selectable clips and validates operator-supplied uploads, so any
footage can be run through the pipeline without editing config or restarting
the backend.

Everything stays on the local filesystem. Nothing is uploaded anywhere.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import AsyncIterator
from pathlib import Path

import cv2

from backend.schemas import VideoInfo

log = logging.getLogger(__name__)


class UploadTooLarge(ValueError):
    """An upload exceeded the configured size limit.

    Distinct from a plain ValueError so the API can answer 413 rather than
    400 without matching on the message text.
    """


class VideoLibrary:
    """Lists, probes and accepts local video files."""

    def __init__(
        self,
        library_dir: Path,
        upload_dir: Path,
        *,
        allowed_suffixes: tuple[str, ...],
        max_upload_mb: int = 2048,
    ) -> None:
        self.library_dir = Path(library_dir)
        self.upload_dir = Path(upload_dir)
        self.allowed_suffixes = {s.lower() for s in allowed_suffixes}
        self.max_upload_mb = max_upload_mb
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_videos(self, active_path: Path | None = None) -> list[VideoInfo]:
        """Every playable clip in the library, newest upload first."""
        seen: dict[Path, VideoInfo] = {}

        for path in sorted(self.library_dir.rglob("*")):
            if not self._is_video(path):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen[resolved] = self._describe(path, active_path)

        # Uploads first (most recently added at the top), then bundled clips.
        uploads = [v for v in seen.values() if v.uploaded]
        bundled = [v for v in seen.values() if not v.uploaded]
        uploads.sort(key=lambda v: Path(v.path).stat().st_mtime, reverse=True)
        bundled.sort(key=lambda v: v.name)
        return uploads + bundled

    def _is_video(self, path: Path) -> bool:
        return (
            path.is_file()
            and path.suffix.lower() in self.allowed_suffixes
            and not path.name.startswith(".")
        )

    def _describe(self, path: Path, active_path: Path | None) -> VideoInfo:
        width = height = 0
        fps = 0.0
        duration = 0.0

        # Probing opens the file; a corrupt clip must not break the listing.
        try:
            cap = cv2.VideoCapture(str(path))
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
                frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
                if fps > 0 and frames > 0:
                    duration = frames / fps
            cap.release()
        except Exception:
            log.warning("Could not probe video %s", path, exc_info=True)

        try:
            is_active = active_path is not None and path.resolve() == active_path.resolve()
        except OSError:
            is_active = False

        return VideoInfo(
            name=path.name,
            path=str(path),
            size_mb=round(path.stat().st_size / 1e6, 1),
            duration=round(duration, 1),
            width=width,
            height=height,
            fps=round(fps, 1),
            is_active=is_active,
            uploaded=self._is_upload(path),
        )

    def _is_upload(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.upload_dir.resolve())
            return True
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Resolution and validation
    # ------------------------------------------------------------------

    def resolve(self, raw_path: str) -> Path:
        """Resolve a client-supplied path to a real, playable video.

        Raises ValueError with an operator-readable message on rejection.

        Accepts an absolute path anywhere on this machine deliberately: the
        operator asked to test arbitrary local footage, and this backend binds
        to localhost only. It still verifies the file exists, is a regular
        file, and has a video extension, so a stray path cannot be handed to
        OpenCV.
        """
        candidate = Path(raw_path).expanduser()

        if not candidate.is_absolute():
            candidate = (self.library_dir / candidate).resolve()

        if not candidate.exists():
            raise ValueError(f"No such file: {candidate}")
        if not candidate.is_file():
            raise ValueError(f"Not a file: {candidate}")
        if candidate.suffix.lower() not in self.allowed_suffixes:
            raise ValueError(
                f"Unsupported format '{candidate.suffix}'. "
                f"Supported: {', '.join(sorted(self.allowed_suffixes))}"
            )
        if not self.is_playable(candidate):
            raise ValueError(f"Could not decode '{candidate.name}'. It may be corrupt.")

        return candidate

    @staticmethod
    def is_playable(path: Path) -> bool:
        """Whether OpenCV can open the file and read one frame."""
        try:
            cap = cv2.VideoCapture(str(path))
            if not cap.isOpened():
                cap.release()
                return False
            ok, _ = cap.read()
            cap.release()
            return bool(ok)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def safe_upload_path(self, filename: str) -> Path:
        """A safe destination inside the upload directory.

        The client controls this filename, so it is stripped to a basename and
        sanitised - a name like "../../etc/passwd.mp4" must never escape the
        upload directory.
        """
        base = Path(filename or "upload.mp4").name
        stem = Path(base).stem
        suffix = Path(base).suffix.lower()

        if suffix not in self.allowed_suffixes:
            raise ValueError(
                f"Unsupported format '{suffix or 'unknown'}'. "
                f"Supported: {', '.join(sorted(self.allowed_suffixes))}"
            )

        # Normalise unicode and keep only benign characters.
        stem = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-") or "upload"
        stem = stem[:80]

        destination = self.upload_dir / f"{stem}{suffix}"
        counter = 1
        while destination.exists():
            destination = self.upload_dir / f"{stem}_{counter}{suffix}"
            counter += 1

        # Belt and braces: confirm the result really is inside upload_dir.
        resolved_parent = destination.resolve().parent
        if resolved_parent != self.upload_dir.resolve():
            raise ValueError("Invalid upload filename.")

        return destination

    async def save_upload(
        self, filename: str, chunks: AsyncIterator[bytes]
    ) -> tuple[Path, int]:
        """Stream an uploaded clip to disk and validate it.

        Returns (path, bytes_written). Raises `UploadTooLarge` or `ValueError`
        with an operator-readable message; in every failure case the partial
        file is removed, so a rejected upload never lingers in the library.

        Written in chunks rather than read whole: demo footage runs to
        hundreds of megabytes and must not be held in memory.
        """
        destination = self.safe_upload_path(filename)
        max_bytes = self.max_upload_mb * 1024 * 1024
        written = 0

        try:
            with destination.open("wb") as out:
                async for chunk in chunks:
                    written += len(chunk)
                    if written > max_bytes:
                        raise UploadTooLarge(f"File exceeds the {self.max_upload_mb} MB limit.")
                    out.write(chunk)

            # A file that cannot be decoded must not become the active source,
            # or the operator gets a black screen with no explanation.
            if not self.is_playable(destination):
                raise ValueError(f"Could not decode '{filename}'. Try an H.264 MP4.")
        except BaseException:
            destination.unlink(missing_ok=True)
            raise

        return destination, written

    def resolve_upload(self, name: str) -> Path:
        """Resolve an uploaded clip by name, for deletion.

        The name is reduced to a basename and the result is confirmed to sit
        inside the upload directory, so a traversal cannot reach anything
        else on disk.
        """
        target = self.upload_dir / Path(name).name

        if not target.exists() or not target.is_file():
            raise FileNotFoundError(f"No uploaded file named '{name}'.")
        if target.resolve().parent != self.upload_dir.resolve():
            raise ValueError("Invalid filename.")

        return target

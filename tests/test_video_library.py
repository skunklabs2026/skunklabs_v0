"""Video library: listing, validation, upload safety, and runtime switching."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.video.library import VideoLibrary

SUFFIXES = (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm")


@pytest.fixture
def library(tmp_path: Path) -> VideoLibrary:
    return VideoLibrary(
        tmp_path / "videos",
        tmp_path / "videos" / "uploads",
        allowed_suffixes=SUFFIXES,
    )


class TestUploadSafety:
    def test_traversal_is_neutralised(self, library):
        """A traversal filename must not escape the upload directory."""
        destination = library.safe_upload_path("../../../../etc/passwd.mp4")
        assert destination.parent == library.upload_dir
        assert "passwd" in destination.name

    def test_absolute_path_is_reduced_to_basename(self, library):
        destination = library.safe_upload_path("/etc/evil.mp4")
        assert destination.parent == library.upload_dir
        assert destination.name == "evil.mp4"

    def test_disallowed_extension_rejected(self, library):
        with pytest.raises(ValueError, match="Unsupported format"):
            library.safe_upload_path("payload.sh")

    def test_no_extension_rejected(self, library):
        with pytest.raises(ValueError):
            library.safe_upload_path("payload")

    def test_exotic_characters_sanitised(self, library):
        destination = library.safe_upload_path("dröne clip #1 (final).mp4")
        assert destination.parent == library.upload_dir
        assert all(c.isalnum() or c in "._-" for c in destination.stem)

    def test_collisions_get_unique_names(self, library):
        first = library.safe_upload_path("clip.mp4")
        first.write_bytes(b"x")
        second = library.safe_upload_path("clip.mp4")
        assert second != first
        assert second.stem.startswith("clip")


class TestResolve:
    def test_missing_file_rejected(self, library):
        with pytest.raises(ValueError, match="No such file"):
            library.resolve("/definitely/not/here.mp4")

    def test_directory_rejected(self, library, tmp_path):
        with pytest.raises(ValueError, match="Not a file"):
            library.resolve(str(tmp_path))

    def test_bad_extension_rejected(self, library, tmp_path):
        script = tmp_path / "evil.sh"
        script.write_text("#!/bin/sh\n")
        with pytest.raises(ValueError, match="Unsupported format"):
            library.resolve(str(script))

    def test_undecodable_file_rejected(self, library, tmp_path):
        """A file with the right extension but junk contents must be caught."""
        fake = tmp_path / "notreally.mp4"
        fake.write_bytes(b"this is not a video")
        with pytest.raises(ValueError, match="Could not decode"):
            library.resolve(str(fake))


class TestListing:
    def test_empty_library(self, library):
        assert library.list_videos() == []

    def test_ignores_non_video_files(self, library):
        (library.library_dir / "notes.txt").write_text("hello")
        (library.library_dir / ".hidden.mp4").write_bytes(b"x")
        assert library.list_videos() == []

    def test_lists_real_video(self, library):
        """Uses the generated demo clip, which is a genuine decodable file."""
        demo = Path(__file__).resolve().parents[1] / "assets" / "videos" / "demo_drone.mp4"
        if not demo.exists():
            pytest.skip("demo clip not generated")

        import shutil

        copied = library.library_dir / "demo.mp4"
        shutil.copy(demo, copied)

        videos = library.list_videos(active_path=copied)
        assert len(videos) == 1
        assert videos[0].name == "demo.mp4"
        assert videos[0].is_active
        assert videos[0].width > 0
        assert videos[0].duration > 0

    def test_uploads_are_flagged(self, library):
        demo = Path(__file__).resolve().parents[1] / "assets" / "videos" / "demo_drone.mp4"
        if not demo.exists():
            pytest.skip("demo clip not generated")

        import shutil

        shutil.copy(demo, library.upload_dir / "mine.mp4")
        videos = library.list_videos()
        assert videos[0].uploaded is True


class TestSourceApi:
    """The HTTP surface for loading arbitrary footage."""

    def test_source_status_lists_library(self, client):
        body = client.get("/api/source").json()
        assert body["video_source"] in ("file", "camera")
        assert isinstance(body["videos"], list)
        assert "motion" in body["detectors_available"]

    def test_select_missing_video_rejected(self, client):
        response = client.post("/api/source/video", json={"path": "/nope/missing.mp4"})
        assert response.status_code == 400
        assert "No such file" in response.json()["detail"]

    def test_select_non_video_rejected(self, client, tmp_path):
        script = tmp_path / "x.sh"
        script.write_text("echo hi")
        response = client.post("/api/source/video", json={"path": str(script)})
        assert response.status_code == 400

    def test_unknown_detector_rejected(self, client):
        response = client.post("/api/source/detector", json={"detector": "magic"})
        assert response.status_code == 400

    def test_upload_rejects_bad_extension(self, client):
        response = client.post(
            "/api/source/upload",
            files={"file": ("evil.sh", b"#!/bin/sh", "application/x-sh")},
        )
        assert response.status_code == 400

    def test_upload_rejects_undecodable_content(self, client):
        """Right extension, junk bytes - must not become the active source."""
        response = client.post(
            "/api/source/upload",
            files={"file": ("broken.mp4", b"not a video at all", "video/mp4")},
        )
        assert response.status_code == 400
        assert "decode" in response.json()["detail"].lower()

    def test_upload_and_switch(self, client):
        """A real clip uploads, becomes active, and the pipeline keeps running."""
        demo = Path(__file__).resolve().parents[1] / "assets" / "videos" / "demo_drone.mp4"
        if not demo.exists():
            pytest.skip("demo clip not generated")

        response = client.post(
            "/api/source/upload",
            files={"file": ("operator_clip.mp4", demo.read_bytes(), "video/mp4")},
        )
        assert response.status_code == 200, response.text
        assert response.json()["ok"] is True

        import time

        # Give the worker thread a moment to apply the queued swap.
        for _ in range(60):
            status = client.get("/api/source").json()
            if status["active_video"] and "operator_clip" in status["active_video"]:
                break
            time.sleep(0.1)

        assert "operator_clip" in (status["active_video"] or "")

        # And the pipeline must still be producing frames from the new source.
        for _ in range(60):
            telemetry = client.get("/api/telemetry").json()
            if telemetry and telemetry["system"]["frame_index"] > 2:
                break
            time.sleep(0.1)
        assert telemetry["system"]["frame_index"] > 2

    def test_delete_active_upload_is_refused(self, client):
        """Deleting the clip currently playing would strand the pipeline."""
        demo = Path(__file__).resolve().parents[1] / "assets" / "videos" / "demo_drone.mp4"
        if not demo.exists():
            pytest.skip("demo clip not generated")

        client.post(
            "/api/source/upload",
            files={"file": ("active_clip.mp4", demo.read_bytes(), "video/mp4")},
        )

        import time

        for _ in range(60):
            status = client.get("/api/source").json()
            if status["active_video"] and "active_clip" in status["active_video"]:
                break
            time.sleep(0.1)

        response = client.delete("/api/source/upload/active_clip.mp4")
        assert response.status_code == 409

    def test_delete_missing_upload_404s(self, client):
        assert client.delete("/api/source/upload/ghost.mp4").status_code == 404

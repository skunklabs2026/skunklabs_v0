import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { VideoLibrary } from "./VideoLibrary";
import { makeVideo } from "../../test/factories";

const base = {
  videos: [makeVideo()],
  busy: false,
  onSelect: vi.fn(),
  onRemove: vi.fn(),
  loaded: true,
};

const library = (props: Partial<typeof base> = {}) =>
  render(<VideoLibrary {...base} {...props} />).container;

describe("VideoLibrary", () => {
  it("invites the operator to add a clip when the library is empty", () => {
    library({ videos: [], loaded: true });
    expect(
      screen.getByText("No clips yet. Drop one above to get started."),
    ).toBeInTheDocument();
  });

  // Before the first status arrives, "no clips" would be a lie.
  it("says nothing until the library has actually loaded", () => {
    const container = library({ videos: [], loaded: false });
    expect(screen.queryByText(/No clips yet/)).not.toBeInTheDocument();
    expect(container.querySelector(".video-list")).toBeInTheDocument();
  });

  it("lists each clip with its dimensions, duration and size", () => {
    library({
      videos: [
        makeVideo({
          name: "approach.mp4",
          width: 960,
          height: 540,
          duration: 24,
          size_mb: 2.6,
        }),
      ],
    });
    expect(screen.getByText("approach.mp4")).toBeInTheDocument();
    expect(screen.getByText(/960×540 · 24s · 2.6 MB/)).toBeInTheDocument();
  });

  it("shows ? for dimensions it could not read", () => {
    library({ videos: [makeVideo({ width: 0, height: 0 })] });
    expect(screen.getByText(/\? ·/)).toBeInTheDocument();
  });

  it("marks an uploaded clip as such", () => {
    library({ videos: [makeVideo({ uploaded: true })] });
    expect(screen.getByText(/· uploaded/)).toBeInTheDocument();
  });

  it("exposes the full path as a tooltip", () => {
    const container = library({ videos: [makeVideo({ path: "/clips/a.mp4" })] });
    expect(container.querySelector(".video-pick")).toHaveAttribute(
      "title",
      "/clips/a.mp4",
    );
  });

  it("highlights the clip currently in use", () => {
    const container = library({
      videos: [
        makeVideo({ name: "a.mp4" }),
        makeVideo({ name: "b.mp4", path: "/b", is_active: true }),
      ],
    });
    const active = container.querySelectorAll(".video-item.is-active");
    expect(active).toHaveLength(1);
    expect(active[0]).toHaveTextContent("b.mp4");
  });

  it("selects a clip, passing the whole VideoInfo", () => {
    const onSelect = vi.fn();
    const video = makeVideo({ name: "approach.mp4" });
    library({ videos: [video], onSelect });
    fireEvent.click(screen.getByText("approach.mp4"));
    expect(onSelect).toHaveBeenCalledWith(video);
  });

  describe("deletion", () => {
    it("offers delete on an uploaded, inactive clip", () => {
      library({
        videos: [makeVideo({ name: "mine.mp4", uploaded: true, is_active: false })],
      });
      expect(
        screen.getByRole("button", { name: "Delete mine.mp4" }),
      ).toBeInTheDocument();
    });

    // Bundled footage is not the operator's to delete.
    it("does not offer delete on a clip that was not uploaded", () => {
      library({ videos: [makeVideo({ uploaded: false })] });
      expect(
        screen.queryByRole("button", { name: /^Delete/ }),
      ).not.toBeInTheDocument();
    });

    // Deleting the clip being replayed would pull the source out from under
    // the running pipeline.
    it("does not offer delete on the clip currently in use", () => {
      library({ videos: [makeVideo({ uploaded: true, is_active: true })] });
      expect(
        screen.queryByRole("button", { name: /^Delete/ }),
      ).not.toBeInTheDocument();
    });

    it("removes by name", () => {
      const onRemove = vi.fn();
      library({
        videos: [makeVideo({ name: "mine.mp4", uploaded: true })],
        onRemove,
      });
      fireEvent.click(screen.getByRole("button", { name: "Delete mine.mp4" }));
      expect(onRemove).toHaveBeenCalledWith("mine.mp4");
    });
  });

  it("disables every control while a change is in flight", () => {
    const container = library({
      videos: [makeVideo({ uploaded: true })],
      busy: true,
    });
    container.querySelectorAll("button").forEach((b) => expect(b).toBeDisabled());
  });
});

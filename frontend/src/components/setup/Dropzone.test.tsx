import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Dropzone } from "./Dropzone";

const file = (name = "clip.mp4") => new File(["data"], name, { type: "video/mp4" });

function setup(props: Partial<Parameters<typeof Dropzone>[0]> = {}) {
  const onFile = vi.fn();
  const container = render(
    <Dropzone onFile={onFile} percent={null} {...props} />,
  ).container;
  const zone = screen.getByRole("button", { name: "Upload a video" });
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  return { onFile, container, zone, input };
}

describe("Dropzone", () => {
  it("explains both ways to load a clip, and which formats", () => {
    setup();
    expect(screen.getByText("Drop a video here")).toBeInTheDocument();
    expect(
      screen.getByText(/or click to browse · MP4, MOV, M4V, AVI, MKV, WEBM/),
    ).toBeInTheDocument();
  });

  it("accepts a dropped file", () => {
    const { onFile, zone } = setup();
    const dropped = file();
    fireEvent.drop(zone, { dataTransfer: { files: [dropped] } });
    expect(onFile).toHaveBeenCalledWith(dropped);
  });

  it("ignores a drop with no files", () => {
    const { onFile, zone } = setup();
    fireEvent.drop(zone, { dataTransfer: { files: [] } });
    expect(onFile).not.toHaveBeenCalled();
  });

  it("highlights while a file is dragged over, and stops on leave", () => {
    const { zone } = setup();
    expect(zone).not.toHaveClass("is-dragging");

    fireEvent.dragOver(zone);
    expect(zone).toHaveClass("is-dragging");

    fireEvent.dragLeave(zone);
    expect(zone).not.toHaveClass("is-dragging");
  });

  it("stops highlighting once the file is dropped", () => {
    const { zone } = setup();
    fireEvent.dragOver(zone);
    fireEvent.drop(zone, { dataTransfer: { files: [file()] } });
    expect(zone).not.toHaveClass("is-dragging");
  });

  it("opens the file picker on click", () => {
    const { zone, input } = setup();
    const click = vi.spyOn(input, "click");
    fireEvent.click(zone);
    expect(click).toHaveBeenCalled();
  });

  it.each(["Enter", " "])("opens the file picker on %s", (key) => {
    const { zone, input } = setup();
    const click = vi.spyOn(input, "click");
    fireEvent.keyDown(zone, { key });
    expect(click).toHaveBeenCalled();
  });

  it("ignores other keys", () => {
    const { zone, input } = setup();
    const click = vi.spyOn(input, "click");
    fireEvent.keyDown(zone, { key: "a" });
    expect(click).not.toHaveBeenCalled();
  });

  it("does not open the picker when disabled", () => {
    const { zone, input } = setup({ disabled: true });
    const click = vi.spyOn(input, "click");
    fireEvent.click(zone);
    fireEvent.keyDown(zone, { key: "Enter" });
    expect(click).not.toHaveBeenCalled();
  });

  it("accepts a browsed file and clears the input so the same file can be re-picked", () => {
    const { onFile, input } = setup();
    const picked = file();
    fireEvent.change(input, { target: { files: [picked] } });
    expect(onFile).toHaveBeenCalledWith(picked);
    expect(input.value).toBe("");
  });

  it("restricts the picker to video files", () => {
    const { input } = setup();
    expect(input).toHaveAttribute("accept", "video/*");
  });

  it("is reachable and operable from the keyboard", () => {
    const { zone } = setup();
    expect(zone).toHaveAttribute("tabIndex", "0");
  });

  describe("progress", () => {
    it("is hidden when nothing is uploading", () => {
      const { container } = setup({ percent: null });
      expect(container.querySelector(".dropzone-progress")).toBeNull();
    });

    it("shows the percentage while uploading", () => {
      setup({ percent: 42 });
      expect(screen.getByText("42%")).toBeInTheDocument();
    });

    // 0 is a real value, not "no upload" — it must still render.
    it("shows 0% at the very start of an upload", () => {
      const { container } = setup({ percent: 0 });
      expect(container.querySelector(".dropzone-progress")).toBeInTheDocument();
      expect(screen.getByText("0%")).toBeInTheDocument();
    });
  });
});

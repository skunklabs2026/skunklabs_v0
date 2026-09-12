import { CanvasTexture, SRGBColorSpace } from "three";

/**
 * A compass rose for the ground under the launcher, drawn once to a canvas.
 * Canvas top is north (−Z once the plane is laid flat), right is east.
 */
export function createCompassTexture(size = 1024): CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const c = size / 2;
  const outer = size * 0.46;

  ctx.strokeStyle = "rgba(150, 175, 200, 0.28)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(c, c, outer, 0, Math.PI * 2);
  ctx.stroke();

  ctx.setLineDash([4, 10]);
  ctx.beginPath();
  ctx.arc(c, c, size * 0.3, 0, Math.PI * 2);
  ctx.stroke();
  ctx.setLineDash([]);

  for (let deg = 0; deg < 360; deg += 5) {
    const major = deg % 30 === 0;
    const rad = ((deg - 90) * Math.PI) / 180;
    const inner = outer - (major ? 34 : deg % 10 === 0 ? 20 : 11);
    ctx.strokeStyle = major
      ? "rgba(190, 210, 230, 0.6)"
      : "rgba(150, 175, 200, 0.3)";
    ctx.lineWidth = major ? 3 : 2;
    ctx.beginPath();
    ctx.moveTo(c + Math.cos(rad) * inner, c + Math.sin(rad) * inner);
    ctx.lineTo(c + Math.cos(rad) * outer, c + Math.sin(rad) * outer);
    ctx.stroke();
  }

  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  const labels: [number, string][] = [
    [0, "N"],
    [90, "E"],
    [180, "S"],
    [270, "W"],
    [30, "030"],
    [60, "060"],
    [120, "120"],
    [150, "150"],
    [210, "210"],
    [240, "240"],
    [300, "300"],
    [330, "330"],
  ];
  for (const [deg, text] of labels) {
    const cardinal = text.length === 1;
    const rad = ((deg - 90) * Math.PI) / 180;
    const r = outer - 66;
    ctx.font = `${cardinal ? 600 : 500} ${cardinal ? 40 : 24}px "IBM Plex Mono", monospace`;
    ctx.fillStyle = cardinal
      ? "rgba(220, 232, 242, 0.85)"
      : "rgba(160, 180, 200, 0.55)";
    ctx.fillText(text, c + Math.cos(rad) * r, c + Math.sin(rad) * r);
  }

  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

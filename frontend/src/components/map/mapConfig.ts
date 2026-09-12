/**
 * Map appearance. Positions and motion come from the backend
 * (backend/scenario/config.py); this file only decides how they are drawn.
 */

const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";

export const MAP_TILES = {
  /** Satellite imagery, lightly toned down in CSS (.c-pane-imagery). */
  imagery: {
    url: `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`,
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
    maxNativeZoom: 18,
  },
  /** Roads over the imagery, so the area reads as a real place. */
  roads: {
    url: `${ESRI}/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}`,
  },
  /** Boundaries and place names. */
  places: {
    url: `${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`,
    attribution: "Labels © Esri",
  },
};

/**
 * Tiles are the only thing on the page that needs the internet. Build with
 * VITE_MAP_TILES=off for a fully offline console: the site, protected radius,
 * nodes, coverage and threats still draw on a dark ground.
 */
export const TILES_ENABLED = import.meta.env.VITE_MAP_TILES !== "off";

export const MAP_VIEW = {
  /** Opening view: centred on the site, this far to each edge - room for the threats' approach. */
  fitRadiusKm: 52,
  /** Short ray showing where each node currently points. */
  nodeHeadingRayKm: 6,
  /** Direction-of-travel leader drawn ahead of each threat. */
  trackLeaderKm: 4,
};

export const MAP_COLORS = {
  site: "#5aa9ff",
  coverage: "#37d483",
  heading: "#37d483",
  requested: "#e9b44c",
  track: "#ff5a52",
  proposed: "#e9b44c",
  authorized: "#5aa9ff",
  interceptor: "#f1f6fb",
};

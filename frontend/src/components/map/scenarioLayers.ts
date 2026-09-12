/**
 * Everything drawn on the Leaflet map, updated in place from each snapshot.
 *
 * Plain Leaflet, no React: the map subscribes to the store directly, so a
 * 20 Hz snapshot stream moves markers without re-rendering components. Layers
 * are created once per object and mutated; objects that disappear (a reset)
 * have their layers removed.
 *
 * Drawn, bottom to top: node coverage (the defended area), the protected
 * radius, the site, nodes and their headings, response lines, threats,
 * interceptors, intercept markers.
 */

import L from "leaflet";
import type {
  DefenseNode,
  Engagement,
  EngagementStatus,
  GeoPoint,
  ProtectedSite,
  ScenarioSnapshot,
  SimulatedInterceptor,
  Track,
} from "../../scenario/contract";
import { destination, shortestDelta } from "../../scenario/geo";
import { findNode, findTrack } from "../../scenario/select";
import { MAP_COLORS, MAP_TILES, MAP_VIEW, TILES_ENABLED } from "./mapConfig";

type LatLngTuple = [number, number];

const SITE_ICON = `
  <div class="c-mk c-mk-site">
    <svg viewBox="0 0 26 26"><rect x="3.5" y="3.5" width="19" height="19" rx="1.5" fill="rgba(90,169,255,0.3)" stroke="#5aa9ff" stroke-width="1.8"/><path d="M8.5 18.5v-6h3v6M13.5 18.5v-10h4v10" fill="none" stroke="#e6f0ff" stroke-width="1.4"/></svg>
    <div class="c-mk-label"><b data-f="id"></b><span data-f="name"></span></div>
  </div>`;

const NODE_ICON = `
  <div class="c-mk c-mk-node">
    <span class="c-node-dot"></span>
    <div class="c-mk-label"><b data-f="id"></b><span data-f="inv"></span></div>
  </div>`;

const TRACK_ICON = `
  <div class="c-mk c-mk-track">
    <div class="c-mk-diamond"></div>
    <div class="c-mk-label"><b data-f="id"></b><span data-f="dist"></span></div>
  </div>`;

const INTERCEPTOR_ICON = `
  <div class="c-mk c-mk-interceptor">
    <svg viewBox="0 0 22 22"><path data-f="chevron" d="M11 1.5 17.5 19 11 14.8 4.5 19Z" fill="#f1f6fb" stroke="#05090f" stroke-width="1"/></svg>
    <div class="c-mk-label"><b data-f="id"></b></div>
  </div>`;

const INTERCEPT_ICON = `
  <div class="c-mk c-mk-hit">
    <span class="c-ring"></span><span class="c-ring"></span>
    <div class="c-mk-label" data-f="label"></div>
  </div>`;

const ACTIVE_RESPONSE: ReadonlySet<EngagementStatus> = new Set([
  "PROPOSED",
  "AWAITING_AUTHORIZATION",
  "AUTHORIZED",
  "IN_FLIGHT",
]);
const UNDECIDED: ReadonlySet<EngagementStatus> = new Set([
  "PROPOSED",
  "AWAITING_AUTHORIZATION",
]);

function divIcon(html: string): L.DivIcon {
  // A zero-size icon anchored at the point; CSS positions the parts.
  return L.divIcon({ html, className: "", iconSize: [0, 0] });
}

function part<E extends Element = Element>(
  marker: L.Marker,
  selector: string,
): E | null {
  return marker.getElement()?.querySelector<E>(selector) ?? null;
}

function setText(marker: L.Marker, field: string, text: string) {
  const element = part(marker, `[data-f="${field}"]`);
  if (element && element.textContent !== text) element.textContent = text;
}

function show(map: L.Map, marker: L.Marker, at: LatLngTuple) {
  marker.setLatLng(at);
  if (!map.hasLayer(marker)) marker.addTo(map);
}

const latLng = (p: { latitude: number; longitude: number }): LatLngTuple => [
  p.latitude,
  p.longitude,
];
const toLatLngs = (points: GeoPoint[]): LatLngTuple[] => points.map(latLng);

/** Create, update and remove one layer per object, keyed by id. */
function syncLayers<T extends { id: string }, V>(
  layers: Map<string, V>,
  items: readonly T[],
  create: (item: T) => V,
  update: (layer: V, item: T) => void,
  remove: (layer: V) => void,
) {
  const present = new Set<string>();
  for (const item of items) {
    present.add(item.id);
    let layer = layers.get(item.id);
    if (layer === undefined) {
      layer = create(item);
      layers.set(item.id, layer);
    }
    update(layer, item);
  }
  for (const [id, layer] of layers) {
    if (present.has(id)) continue;
    remove(layer);
    layers.delete(id);
  }
}

export function createTacticalMap(
  container: HTMLElement,
  site: ProtectedSite,
): L.Map {
  const map = L.map(container, {
    zoomControl: false,
    attributionControl: true,
    zoomSnap: 0.25,
    minZoom: 6,
    maxZoom: 16,
  });
  map.createPane("imagery").classList.add("c-pane-imagery");
  map.getPane("imagery")!.style.zIndex = "200";

  if (TILES_ENABLED) {
    L.tileLayer(MAP_TILES.imagery.url, {
      pane: "imagery",
      attribution: MAP_TILES.imagery.attribution,
      maxNativeZoom: MAP_TILES.imagery.maxNativeZoom,
    }).addTo(map);
    L.tileLayer(MAP_TILES.roads.url, { opacity: 0.55 }).addTo(map);
    L.tileLayer(MAP_TILES.places.url, {
      attribution: MAP_TILES.places.attribution,
      opacity: 0.9,
    }).addTo(map);
  }

  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.control.scale({ position: "bottomleft", imperial: false }).addTo(map);
  map.attributionControl.setPrefix(false);

  map.fitBounds(L.latLng(latLng(site)).toBounds(MAP_VIEW.fitRadiusKm * 2000));
  return map;
}

interface NodeLayer {
  marker: L.Marker;
  heading: L.Polyline;
  requested: L.Polyline;
}

interface TrackLayer {
  marker: L.Marker;
  trail: L.Polyline;
  leader: L.Polyline;
}

interface InterceptorLayer {
  marker: L.Marker;
  trail: L.Polyline;
}

type Intercepted = Engagement & { intercept_point: GeoPoint };

export class ScenarioLayers {
  private readonly nodes = new Map<string, NodeLayer>();
  private readonly tracks = new Map<string, TrackLayer>();
  private readonly responses = new Map<string, L.Polyline>();
  private readonly interceptors = new Map<string, InterceptorLayer>();
  private readonly intercepts = new Map<string, L.Marker>();

  constructor(
    private readonly map: L.Map,
    snapshot: ScenarioSnapshot,
    private readonly onNodeClick: (nodeId: string) => void,
  ) {
    const { site } = snapshot;

    // Node coverage: overlapping circles whose union is the defended area.
    for (const node of snapshot.nodes) {
      L.circle(latLng(node), {
        radius: node.coverage_radius_km * 1000,
        color: MAP_COLORS.coverage,
        weight: 1,
        opacity: 0.35,
        fillColor: MAP_COLORS.coverage,
        fillOpacity: 0.07,
        interactive: false,
      }).addTo(map);
    }

    // The protected radius, drawn over the coverage so its edge stays crisp.
    L.circle(latLng(site), {
      radius: site.protected_radius_km * 1000,
      color: MAP_COLORS.site,
      weight: 2.2,
      opacity: 0.95,
      dashArray: "10 8",
      fill: false,
      interactive: false,
    }).addTo(map);
    L.marker(destination(site, 0, site.protected_radius_km), {
      icon: divIcon(
        `<div class="c-mk-area">Protected radius · ${site.protected_radius_km} km</div>`,
      ),
      interactive: false,
      keyboard: false,
    }).addTo(map);

    const siteMarker = L.marker(latLng(site), {
      icon: divIcon(SITE_ICON),
      keyboard: false,
      interactive: false,
      zIndexOffset: 400,
    }).addTo(map);
    setText(siteMarker, "id", site.id);
    setText(siteMarker, "name", site.name);
  }

  /** Redraw from a snapshot. `focusResponseId` is the response being decided now. */
  update(snapshot: ScenarioSnapshot, focusResponseId: string | null): void {
    const focus =
      snapshot.engagements.find((e) => e.id === focusResponseId) ?? null;

    syncLayers(
      this.nodes,
      snapshot.nodes,
      (node) => this.createNode(node),
      (layer, node) => this.updateNode(layer, node, node.id === focus?.node_id),
      (layer) =>
        [layer.marker, layer.heading, layer.requested].forEach((l) => l.remove()),
    );
    syncLayers(
      this.responses,
      snapshot.engagements.filter((e) => ACTIVE_RESPONSE.has(e.status)),
      () => L.polyline([], { interactive: false }).addTo(this.map),
      (line, engagement) =>
        this.updateResponse(
          line,
          engagement,
          snapshot,
          engagement.id === focus?.id,
        ),
      (line) => line.remove(),
    );
    syncLayers(
      this.tracks,
      snapshot.tracks,
      () => this.createTrack(),
      (layer, track) => this.updateTrack(layer, track),
      (layer) =>
        [layer.marker, layer.trail, layer.leader].forEach((l) => l.remove()),
    );
    syncLayers(
      this.interceptors,
      snapshot.interceptors,
      () => this.createInterceptor(),
      (layer, interceptor) => this.updateInterceptor(layer, interceptor),
      (layer) => [layer.marker, layer.trail].forEach((l) => l.remove()),
    );
    syncLayers(
      this.intercepts,
      snapshot.engagements.filter(
        (e): e is Intercepted => e.intercept_point !== null,
      ),
      (engagement) =>
        L.marker(latLng(engagement.intercept_point), {
          icon: divIcon(INTERCEPT_ICON),
          keyboard: false,
          interactive: false,
          zIndexOffset: 1000,
        }).addTo(this.map),
      (marker, engagement) => {
        marker.setLatLng(latLng(engagement.intercept_point));
        setText(marker, "label", `${engagement.track_id} · intercept`);
      },
      (marker) => marker.remove(),
    );
  }

  private createNode(node: DefenseNode): NodeLayer {
    const marker = L.marker(latLng(node), {
      icon: divIcon(NODE_ICON),
      keyboard: false,
      zIndexOffset: 600,
      title: `${node.id} - open in the launcher view`,
    }).addTo(this.map);
    marker.on("click", () => this.onNodeClick(node.id));
    setText(marker, "id", node.id);
    return {
      marker,
      heading: L.polyline([], {
        color: MAP_COLORS.heading,
        weight: 2,
        opacity: 0.95,
        interactive: false,
      }).addTo(this.map),
      requested: L.polyline([], {
        color: MAP_COLORS.requested,
        weight: 1.5,
        opacity: 0.9,
        dashArray: "3 5",
        interactive: false,
      }).addTo(this.map),
    };
  }

  private updateNode(layer: NodeLayer, node: DefenseNode, focused: boolean) {
    const origin = latLng(node);
    const ray = MAP_VIEW.nodeHeadingRayKm;
    layer.marker.setLatLng(origin);
    layer.heading.setLatLngs([
      origin,
      destination(node, node.current_yaw_deg, ray),
    ]);
    const slewing =
      node.state !== "STANDBY" &&
      Math.abs(shortestDelta(node.current_yaw_deg, node.target_yaw_deg)) > 0.5;
    layer.requested.setLatLngs(
      slewing ? [origin, destination(node, node.target_yaw_deg, ray)] : [],
    );
    setText(layer.marker, "inv", `${node.inventory}/${node.inventory_capacity}`);
    const root = part<HTMLElement>(layer.marker, ".c-mk-node");
    if (root) {
      if (root.dataset.state !== node.state) root.dataset.state = node.state;
      root.classList.toggle("is-focus", focused);
    }
  }

  private updateResponse(
    line: L.Polyline,
    engagement: Engagement,
    snapshot: ScenarioSnapshot,
    focused: boolean,
  ) {
    const node = findNode(snapshot, engagement.node_id);
    const track = findTrack(snapshot, engagement.track_id);
    if (!node || !track) {
      line.setLatLngs([]);
      return;
    }
    line.setLatLngs([latLng(node), latLng(track)]);
    const undecided = UNDECIDED.has(engagement.status);
    line.setStyle({
      color: undecided ? MAP_COLORS.proposed : MAP_COLORS.authorized,
      weight: focused ? 3.5 : 1.6,
      opacity: focused ? 1 : 0.8,
      dashArray: undecided ? "8 6" : "2 6",
    });
  }

  private createTrack(): TrackLayer {
    return {
      marker: L.marker([0, 0], {
        icon: divIcon(TRACK_ICON),
        keyboard: false,
        interactive: false,
        zIndexOffset: 800,
      }),
      trail: L.polyline([], {
        color: MAP_COLORS.track,
        weight: 2,
        opacity: 0.8,
        dashArray: "1 6",
        lineCap: "round",
        interactive: false,
      }).addTo(this.map),
      leader: L.polyline([], {
        color: MAP_COLORS.track,
        weight: 2,
        opacity: 0.95,
        interactive: false,
      }).addTo(this.map),
    };
  }

  private updateTrack(layer: TrackLayer, track: Track) {
    const inbound = track.status === "INBOUND";
    layer.trail.setLatLngs(toLatLngs(track.trail));
    layer.leader.setLatLngs(
      inbound
        ? [
            latLng(track),
            destination(track, track.heading_deg, MAP_VIEW.trackLeaderKm),
          ]
        : [],
    );
    show(this.map, layer.marker, latLng(track));
    setText(layer.marker, "id", track.id);
    setText(
      layer.marker,
      "dist",
      inbound ? `${track.site_distance_km.toFixed(1)} km` : "",
    );
    part(layer.marker, ".c-mk-track")?.classList.toggle("is-resolved", !inbound);
  }

  private createInterceptor(): InterceptorLayer {
    return {
      marker: L.marker([0, 0], {
        icon: divIcon(INTERCEPTOR_ICON),
        keyboard: false,
        interactive: false,
        zIndexOffset: 900,
      }),
      trail: L.polyline([], {
        color: MAP_COLORS.interceptor,
        weight: 1.8,
        opacity: 0.85,
        dashArray: "5 5",
        interactive: false,
      }).addTo(this.map),
    };
  }

  private updateInterceptor(
    layer: InterceptorLayer,
    interceptor: SimulatedInterceptor,
  ) {
    const { state } = interceptor;
    layer.trail.setLatLngs(state === "PENDING" ? [] : toLatLngs(interceptor.trail));

    // In flight: a labelled marker. Stood down: a faded one where it stopped.
    // Pending or the intercepting one: none (the intercept marker takes over).
    if (state !== "IN_FLIGHT" && state !== "STOOD_DOWN") {
      layer.marker.remove();
      return;
    }
    show(this.map, layer.marker, latLng(interceptor));
    setText(layer.marker, "id", interceptor.id);
    part(layer.marker, '[data-f="chevron"]')?.setAttribute(
      "transform",
      `rotate(${interceptor.heading_deg} 11 11)`,
    );
    part(layer.marker, ".c-mk-interceptor")?.classList.toggle(
      "is-stood-down",
      state === "STOOD_DOWN",
    );
  }
}

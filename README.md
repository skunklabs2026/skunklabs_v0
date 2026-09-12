# SkunkLabs Operator Interface - V0

The first version of the SkunkLabs operator interface: what an operator uses
to understand how a protected site is being defended, and to authorize each
response.

The interface is the product. **What is simulated is the world behind it** -
the incoming drones, the external sensor, node movement (no hardware is
connected), interceptor launches, their flight, and the outcome.

```
PROTECTED SITE  →  PROTECTED RADIUS (40 km)  →  SIX DEFENSE NODES  →  INCOMING THREATS
   →  NEAREST NODES ACTIVATE TOGETHER  →  ONE PROPOSED RESPONSE PER THREAT
   →  OPERATOR AUTHORIZES (OR DECLINES) EACH, ONE AT A TIME  →  SIMULATED INTERCEPT
```

Everything runs locally. No database, no cloud services.

> **Scope and safety.** This is a software demonstrator. There is no launcher
> control, no motor or servo command, no fire-control or ballistic calculation,
> no guidance law and no weapon release. Yaw and pitch are display values; an
> interceptor is a map marker that walks toward another map marker. Nothing
> happens without an explicit operator authorization, and even then nothing
> physical happens.

---

## The layout

* **Protected site** - your infrastructure, at **your device's GPS position**
  (the browser asks once). If it refuses or never prompts, the site panel on
  `/map` offers "Use my location" again and manual coordinates, and
  `SKUNK_SITE_LATITUDE` / `SKUNK_SITE_LONGITUDE` pin a default of your own.
* **Protected radius** - 40 km, drawn on the map. Threats crossing it trigger
  the defense.
* **Six defense nodes** - evenly spaced on a 20 km ring around the site, drawn
  as circles coloured by state, each holding **6 interceptors** and showing a
  25 km coverage circle. The union of those circles is the defended area.

## Three threat scenarios

| | Threats |
|---|---|
| **Scenario 1** | 4 drones from the east |
| **Scenario 2** | 3 drones from the east, 3 from the west |
| **Scenario 3** | 4 drones from the north, 2 from the southeast |

Pick one on `/map` (or in the bottom bar) before starting.

---

## The demo in 30 seconds

1. Open **`/map`**: your site, the 40 km protected radius, six nodes and their
   coverage.
2. Choose a scenario and press **Start demo**. The drones appear outside the
   radius and close in.
3. They cross the protected radius together. Each is paired with its **nearest
   free node**, so those nodes activate **simultaneously** and turn toward
   their threat - one proposed response per threat.
4. The **Operator decision** panel presents them **one at a time**: which node,
   which threat, how many interceptors (proposed, adjustable up to that node's
   inventory), then **Authorize simulation** or **Decline**. What is next in
   the queue is listed underneath.
5. Authorized nodes launch a short salvo. Interceptors run out to the threat;
   the first to arrive is the simulated intercept and frees its node.
6. **`/launcher`** shows any node close up - the 3D launcher turning, its local
   camera, yaw and pitch - and follows whichever response you are deciding on.
7. When every threat is resolved the mission completes, and **Reset** returns
   everything to the start.

Threats nobody answers reach the site and are logged as not intercepted.

---

## Run it

```bash
make setup && make demo
```

`make demo` starts the backend and the UI and opens http://localhost:5173/map.
Allow location access when the browser asks, so the site is centred on you. If
you miss the prompt, set the position from the site panel on `/map` while idle.
The pieces separately:

```bash
.venv/bin/python -m backend.main          # backend, http://127.0.0.1:8000
cd frontend && npm run dev                # UI, http://localhost:5173/map
```

As a single process (what a deployment looks like):

```bash
make build && .venv/bin/python -m backend.main   # http://127.0.0.1:8000/map
```

Satellite tiles are the only thing fetched from the internet. Build with
`VITE_MAP_TILES=off` for a fully offline console; the site, radius, nodes,
coverage and threats still draw.

---

## The two views

**`/map` - defense / situational awareness.** *What is threatening the
infrastructure I am defending, and how is the system responding?* The map is
the page: protected site and radius, the six nodes with their coverage and
headings, threats with trails and direction, a line from each node to the
threat it is answering (amber while it awaits your decision, blue once
authorized), interceptors, and intercepts. The side column holds the scenario
picker (before the start), the operator decision, the threat list, the node
list and a short event log.

**`/launcher` - one node, close up.** *What is this node doing, and what
simulated response am I authorizing?* Node tabs on the left (following the
current decision unless you pin one), state, assigned response, yaw and pitch
with current versus requested, and inventory. In the centre, the 3D launcher
and that node's camera. On the right, the same decision panel, so you can
authorize from either view.

The bottom bar carries the mission clock, counters (threats, inside area,
awaiting decision, in flight, intercepted, reached site), a plain-language
status line, and the simulation controls - scenario, start and reset - kept
apart from the operator's own controls.

---

## Architecture

```
backend/scenario/                              the simulated world + the state machines
  config.py        every tunable: layout, threat scenarios, speeds, timings
  track_source.py  TrackSource protocol ← simulated threat layouts   (future: video, radar…)
  simulation.py    DefenseScenario: mission, nodes, responses, world step - pure & deterministic
  service.py       ticks it at 20 Hz on the event loop, publishes whole snapshots
  models.py        the API contract  ──► scripts/gen_types.py ──► frontend/src/scenario/contract.ts
backend/api/routers/scenario.py               REST commands + WS /ws/scenario

frontend/src/
  scenario/store.ts     the single client store: latest snapshot + the operator's local choices
  scenario/select.ts    lookups and tallies over a snapshot (no decisions)
  app/deviceLocation.ts     asks the browser for a position (on load, or on request)
  app/useDeviceLocation.ts  sends the device's GPS position as the site location
  views/MapView.tsx     views/LauncherView.tsx
  components/map/       Leaflet map; layers update imperatively from the store
  components/launcher/  3D scene, model loading, articulation (yaw/pitch contract)
  components/camera/    a node's local sensor: real video stream or simulated view
  components/panels/    decision, threats, nodes, scenario picker, node tabs, readouts, log
  components/shell/     top bar, mission bar, simulation controls
```

Principles:

- **One mission state, on the backend.** The UI holds the latest snapshot and
  renders it. Both views, the 3D model and the map cannot disagree because none
  of them computes state.
- **Interlocks live in the state machine.** `can_start`, `can_configure` and the
  `decision_queue` arrive in the snapshot; a rejected command comes back as a
  409 carrying the state machine's own reason.
- **Every change is one whole snapshot**, with a `revision` so a command
  response and a WebSocket push can never apply out of order.
- **The map and the 3D view do not re-render React per frame.** They read the
  store directly, so 20 Hz updates stay cheap.

---

## State machines

```
Mission   IDLE ──► RUNNING ──► COMPLETE                                    (FAULT)
Node      STANDBY ─► TRACK_RECEIVED ─► ORIENTING ─► READY
                   ─► AUTHORIZED ─► SIMULATED_LAUNCH ─► STANDBY
Response  PROPOSED ─► AWAITING_AUTHORIZATION ─► AUTHORIZED ─► IN_FLIGHT ─► INTERCEPTED
                   └─ DECLINED                 (ABORTED if the threat reaches the site)
```

- **Activation.** A wave rarely crosses the boundary on one tick, so pairing
  waits `assessment_delay_s` after the first crossing, then commits every pair
  at once - nearest node to each threat, closest pair first. Those nodes
  activate together.
- **Authorization is explicit and individual.** A response reaches AUTHORIZED
  only through its own authorize call, and only once its node is READY.
- **Freed nodes take the next threat.** A node released by an intercept or a
  decline is available again; declined threats are not re-proposed.
- **Requested orientation** is the bearing to the threat and its line-of-sight
  elevation, never below a 12° display posture.

---

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/scenario` | current snapshot |
| `POST /api/scenario/configure` `{"scenario_id":"S2","latitude":…,"longitude":…}` | scenario and/or site location (idle only) |
| `POST /api/scenario/start` | START DEMO |
| `POST /api/scenario/responses/{id}/authorize` `{"interceptors":2}` | authorize one response (409 unless its node is READY) |
| `POST /api/scenario/responses/{id}/decline` | decline one response |
| `POST /api/scenario/responses/{id}/reassign` `{"node_id":"NODE-04"}` | give one response to a node the operator picked |
| `POST /api/scenario/reset` | reset, keeping scenario and location |
| `WS /ws/scenario` | one snapshot per change (20 Hz while running, 1 Hz heartbeat when idle) |
| `GET /api/health` | liveness; says whether the video pipeline is running |

---

## Where to change things

| What | Where |
|---|---|
| Protected site, default location, 40 km radius | `backend/scenario/config.py` → `SiteSetup` |
| Pinning the site somewhere without editing code | `SKUNK_SITE_LATITUDE`, `SKUNK_SITE_LONGITUDE`, `SKUNK_SITE_NAME` (see `.env.example`) |
| Node count, ring radius, coverage, 6-interceptor inventory | `config.py` → `NodeSetup` |
| The three threat scenarios (directions and counts) | `config.py` → `SCENARIOS` |
| Threat spawn range, spread, altitude, speed | `config.py` → `TrackSetup` |
| Yaw / pitch slew rates, READY tolerance, minimum elevation | `config.py` → `OrientationSetup` |
| Proposed interceptors, assessment beat, orient and launch delays | `config.py` → `EngagementSetup` |
| Interceptor speed, salvo spacing, intercept radius | `config.py` → `InterceptorSetup` |
| World time scale (×12), completion hold, tick rate | `config.py` → `TimingSetup` |
| Map tiles, opening zoom, colours | `frontend/src/components/map/mapConfig.ts` |
| 3D model file, node names, axis mapping, render smoothing | `frontend/src/components/launcher/modelConfig.ts` |
| Simulated camera field of view | `frontend/src/components/camera/cameraProjection.ts` |

Threats and interceptors move on world time (`time_scale`, default ×12) so a
40 km approach fits a short demo while displayed speeds stay realistic; the top
bar shows the factor. It is sized so a wave crosses the protected radius a few
seconds after the start and the operator then has about a minute to work
through the queue. Node slew runs on wall time.

After changing `backend/scenario/models.py`, run
`.venv/bin/python scripts/gen_types.py` - the TypeScript contract is generated
from the Pydantic models.

---

## Replacing the placeholder launcher with the CAD model

The placeholder is built with the same node names a CAD export must have, so
both go through one code path (`components/launcher/articulation.ts`):

```
ROOT
  BASE              static
  YAW_STAGE         rotates about the vertical axis       ← current_yaw_deg
    PITCH_STAGE     rotates about its horizontal axis     ← current_pitch_deg
      LAUNCHER      canister pack
```

1. Export GLB (or glTF) with that hierarchy - or keep your names and change
   `nodes` in `modelConfig.ts`.
2. Save it as `frontend/public/models/skunk-launcher.glb`.
3. Reload `/launcher`. The chip top-left says **CAD model**; if the file is
   missing or lacks the nodes it says **Placeholder model** and why.
4. Tune `modelConfig.ts`: `transform` for units and up-axis (a Z-up CAD export
   usually needs `rotationDeg: [-90, 0, 0]` and `yaw.axis: "z"`), and
   `yaw` / `pitch` `axis`, `sign`, `offsetDeg` until yaw 000° / pitch 0° points
   the canisters north (away from the default camera) and level.

Rotations are added to each node's authored rest rotation. Draco-compressed
files need a `DRACOLoader` added in `modelSource.ts`.

---

## The video / computer-vision pipeline

Preserved, and no longer the centre of the product. The detector, tracker,
video sources, legacy state machine, recording and their tests are unchanged
under `backend/pipeline/`, `backend/vision/`, `backend/video/`,
`backend/mission/`; the original console lives on at **`/sensor-lab`**.

It is off by default. To run it:

```bash
SKUNK_VIDEO_PIPELINE_ENABLED=true make demo
```

The launcher view then offers the real camera stream (`/api/video`) as a node's
local sensor feed, with the simulated camera one click away. It is the intended
next track source: an adapter that turns a confirmed target into a
`TrackReport` (`backend/scenario/track_source.py`) feeds the same mission.

Full documentation of the pipeline: [docs/sensor-lab.md](docs/sensor-lab.md).

---

## Quality

| Command | What it does |
|---|---|
| `make check` | ruff, eslint + prettier, typecheck, backend and frontend tests - run before a PR |
| `make test` | both test suites |
| `make format` | auto-fix formatting |
| `make build` | production frontend build, served by the backend |

---

## Limitations

- One site and one wave per run; threats fly straight lines at constant speed.
- An interceptor marker steps straight at its threat (display motion, not
  guidance). Flat-earth geometry, no terrain, no altitude in flight.
- World time is compressed ×12 for threats and interceptors.
- Node coverage circles are drawn, but pairing is by distance alone - a node
  can be assigned a threat outside its drawn coverage when nearer nodes are busy.
- The simulated camera is a synthetic view, not rendered imagery.
- Satellite tiles need internet unless built with `VITE_MAP_TILES=off`.
- Geolocation needs a secure context (localhost counts, a bare LAN IP does not)
  and permission; on refusal the configured default stands and the site panel
  takes a position by hand.
- The 3D launcher is a primitive placeholder until the CAD model is dropped in.
- No authentication or operator identity; no run recording for the scenario yet.

"""V0 defense scenario - the simulated world behind the operator interface.

One protected site at the operator's location, six defensive nodes around it,
and a selectable threat scenario. The interaction it demonstrates:

    THREATS ENTER THE PROTECTED AREA → NEAREST NODES ACTIVATE TOGETHER
    → EACH PROPOSED RESPONSE AUTHORIZED (OR DECLINED) BY THE OPERATOR, ONE AT A TIME
    → SIMULATED LAUNCH → SIMULATED INTERCEPT

Where tracks come from is deliberately a seam:

    SIMULATED TRACKS ─┐
                      │
    VIDEO / CAMERA ───┼──>  TrackSource  ──>  DefenseScenario  ──>  UI
                      │
    FUTURE SENSOR ────┘

    config.py        every tunable: layout, threat scenarios, speeds, timings
    geo.py           flat-earth geometry helpers (bearing, range, offsets)
    models.py        the API contract (mirrored to TypeScript)
    track_source.py  TrackSource protocol + the simulated threat layouts
    simulation.py    the state machines and world step - pure, deterministic
    service.py       runs the simulation on the event loop, publishes snapshots

>>> SCOPE <<<
Everything here is visualization. There is no fire control, no ballistics, no
guidance, no actuation. Yaw/pitch are display values; an "interceptor" is a
map marker that walks toward another map marker.
"""

from backend.scenario.config import ScenarioConfig
from backend.scenario.service import ScenarioService
from backend.scenario.simulation import DefenseScenario

__all__ = ["DefenseScenario", "ScenarioConfig", "ScenarioService"]

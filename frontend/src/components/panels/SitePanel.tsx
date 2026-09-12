import { useState, type FormEvent } from "react";
import {
  geolocationAvailable,
  requestDeviceLocation,
} from "../../app/deviceLocation";
import {
  useScenario,
  useScenarioCommands,
  useScenarioStore,
} from "../../scenario/hooks";

/**
 * Where the demo is centred.
 *
 * The browser is asked once on load, but that can be refused or never
 * prompted, so the operator can ask again from here or type a position in.
 * Either way the site and all six nodes move with it.
 */
export function SitePanel() {
  const { snapshot, location, pending, connection } = useScenario();
  const { configure } = useScenarioCommands();
  const store = useScenarioStore();
  const [latitude, setLatitude] = useState("");
  const [longitude, setLongitude] = useState("");

  if (!snapshot) return null;
  const { site } = snapshot;
  const locked =
    !snapshot.can_configure || pending !== null || connection !== "online";
  // The backend marks any operator-supplied position DEVICE, so only this
  // client knows whether it came from the browser or from the form below.
  const placed = site.location_source === "DEVICE";
  const fromBrowser = placed && location === "device";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    configure({ latitude: lat, longitude: lon });
    setLatitude("");
    setLongitude("");
  };

  const status = fromBrowser
    ? "Centred on this device."
    : placed
      ? "Centred on the coordinates you set."
      : location === "locating"
        ? "Asking this browser for its position."
        : location === "unavailable"
          ? "This browser gave no position. Allow location access, or set it below."
          : "Using the configured default position.";

  return (
    <section className="c-panel" aria-label="Protected site">
      <div className="c-panel-head">
        <h2 className="c-panel-title">Protected site</h2>
        <span className={`c-chip${placed ? " is-lit c-tone-ready" : ""}`}>
          {fromBrowser ? "This device" : placed ? "Operator set" : "Default"}
        </span>
      </div>

      <dl className="c-kv">
        <dt>{site.id}</dt>
        <dd>{site.name}</dd>
        <dt>Latitude</dt>
        <dd>{site.latitude.toFixed(5)}</dd>
        <dt>Longitude</dt>
        <dd>{site.longitude.toFixed(5)}</dd>
      </dl>

      <p className="c-hint">{status}</p>

      <div className="c-site-actions">
        <button
          type="button"
          className="c-btn c-btn-small"
          disabled={locked || !geolocationAvailable()}
          title={
            geolocationAvailable()
              ? "Ask this browser for its position"
              : "This browser offers no geolocation"
          }
          onClick={() => void requestDeviceLocation(store)}
        >
          Use my location
        </button>
      </div>

      <form className="c-site-form" onSubmit={submit}>
        <label>
          <span className="c-label">Latitude</span>
          <input
            type="number"
            step="any"
            min={-90}
            max={90}
            placeholder={site.latitude.toFixed(4)}
            value={latitude}
            disabled={locked}
            onChange={(event) => setLatitude(event.target.value)}
          />
        </label>
        <label>
          <span className="c-label">Longitude</span>
          <input
            type="number"
            step="any"
            min={-180}
            max={180}
            placeholder={site.longitude.toFixed(4)}
            value={longitude}
            disabled={locked}
            onChange={(event) => setLongitude(event.target.value)}
          />
        </label>
        <button
          type="submit"
          className="c-btn c-btn-small"
          disabled={locked || latitude === "" || longitude === ""}
        >
          Set
        </button>
      </form>

      {!snapshot.can_configure && (
        <p className="c-hint">Reset the demo to move the site.</p>
      )}
    </section>
  );
}

/**
 * Centres the protected site on the operator's device.
 *
 * Asks the browser for a position once on load; whenever the backend is
 * reachable and a position is known, sends it as the site location. The
 * backend accepts it only while idle, so a reload mid-mission changes nothing,
 * hence `quiet`. Without permission or support, the configured default stands,
 * the map says so, and the site panel offers "Use my location" and manual
 * coordinates: a request made from a click is the one a browser reliably
 * prompts for.
 */

import { useEffect, useState } from "react";
import { useScenarioStore, useScenarioValue } from "../scenario/hooks";
import {
  geolocationAvailable,
  readDevicePosition,
  type DevicePosition,
} from "./deviceLocation";

export function useDeviceLocation(): void {
  const store = useScenarioStore();
  const online = useScenarioValue((state) => state.connection === "online");
  const [position, setPosition] = useState<DevicePosition | null>(null);

  useEffect(() => {
    if (!geolocationAvailable()) {
      store.setLocation("unavailable");
      return;
    }
    let cancelled = false;
    store.setLocation("locating");
    void readDevicePosition().then((found) => {
      if (cancelled) return;
      if (!found) {
        store.setLocation("unavailable");
        return;
      }
      store.setLocation("device");
      setPosition(found);
    });
    return () => {
      cancelled = true;
    };
  }, [store]);

  useEffect(() => {
    if (online && position) {
      void store.command("configure", { body: { ...position }, quiet: true });
    }
  }, [store, online, position]);
}

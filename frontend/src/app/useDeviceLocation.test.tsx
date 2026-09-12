import { waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fakeStore } from "../test/fixtures";
import { renderWithStore } from "../test/render";
import { useDeviceLocation } from "./useDeviceLocation";

function Harness() {
  useDeviceLocation();
  return null;
}

function stubGeolocation(value: unknown) {
  Object.defineProperty(navigator, "geolocation", { value, configurable: true });
}

const position = {
  coords: { latitude: 45.0703, longitude: 7.6869 },
} as GeolocationPosition;

afterEach(() => {
  stubGeolocation(undefined);
});

describe("useDeviceLocation", () => {
  it("centres the site on the device once the backend is reachable", async () => {
    stubGeolocation({
      getCurrentPosition: (success: PositionCallback) => success(position),
    });
    const { store, command, setLocation, set } = fakeStore({
      connection: "connecting",
    });

    renderWithStore(<Harness />, store);

    await waitFor(() => expect(setLocation).toHaveBeenCalledWith("device"));
    expect(command).not.toHaveBeenCalled(); // nothing to send to yet

    set({ connection: "online" });
    await waitFor(() =>
      expect(command).toHaveBeenCalledWith("configure", {
        body: { latitude: 45.0703, longitude: 7.6869 },
        quiet: true,
      }),
    );
  });

  it("leaves the default location when permission is refused", async () => {
    stubGeolocation({
      getCurrentPosition: (
        _success: PositionCallback,
        failure: PositionErrorCallback,
      ) => failure({ code: 1, message: "denied" } as GeolocationPositionError),
    });
    const { store, command, setLocation } = fakeStore();

    renderWithStore(<Harness />, store);

    await waitFor(() =>
      expect(setLocation).toHaveBeenLastCalledWith("unavailable"),
    );
    expect(command).not.toHaveBeenCalled();
  });

  it("copes with a browser that has no geolocation", () => {
    stubGeolocation(undefined);
    const { store, command, setLocation } = fakeStore();

    renderWithStore(<Harness />, store);

    expect(setLocation).toHaveBeenCalledWith("unavailable");
    expect(command).not.toHaveBeenCalled();
  });

  it("re-sends the position after a reconnect", async () => {
    stubGeolocation({
      getCurrentPosition: (success: PositionCallback) => success(position),
    });
    const { store, command, set } = fakeStore({ connection: "online" });

    // Already online when the position lands: it goes out on the next render.
    renderWithStore(<Harness />, store);
    await waitFor(() => expect(command).toHaveBeenCalledTimes(1));

    set({ connection: "offline" });
    set({ connection: "online" });
    await waitFor(() => expect(command).toHaveBeenCalledTimes(2));
  });

  it("does not ask the browser twice", async () => {
    const getCurrentPosition = vi.fn((success: PositionCallback) =>
      success(position),
    );
    stubGeolocation({ getCurrentPosition });
    const { store, set } = fakeStore();

    renderWithStore(<Harness />, store);
    set({ connection: "offline" });
    set({ connection: "online" });

    await waitFor(() => expect(getCurrentPosition).toHaveBeenCalledTimes(1));
  });
});

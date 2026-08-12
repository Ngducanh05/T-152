import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type {
  ParkingMap as ParkingMapData,
} from "@/lib/types";
import { canonicalMap, parkingStatus } from "@/test/fixtures";

import { ParkingMap } from "./ParkingMap";

afterEach(cleanup);

function fixture() {
  const map: ParkingMapData = canonicalMap;
  return { map, slots: map.slots, status: parkingStatus };
}

describe("ParkingMap", () => {
  it("renders all 40 canonical slots including zone D and structured highlights", () => {
    const { map, slots, status } = fixture();

    render(
      <ParkingMap
        map={map}
        slots={slots}
        status={status}
        recommendedSlotIds={["F1-D01"]}
        selectedSlotId="F1-A02"
        activeReservationSlotId="F1-A01"
        parkedVehicleSlotId="F1-B01"
        currentLocationNodeId="F1-CP1"
      />,
    );

    expect(screen.getAllByRole("button", { name: /Parking slot/ })).toHaveLength(40);
    expect(screen.getByRole("button", { name: /F1-D10, Zone D/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /F1-A01.*Reserved.*Active reservation/ }).getAttribute("data-status")).toBe("RESERVED");
    expect(screen.getByRole("button", { name: /F1-D01.*EV charger.*Recommended/ })).toBeDefined();
    expect(screen.getByTestId("current-location")).toBeDefined();
  });

  it("positions slots from their own node and renders only the supplied route polyline", () => {
    const { map, slots, status } = fixture();

    render(
      <ParkingMap
        map={map}
        slots={slots}
        status={status}
        route={{
          path: ["F1-CP1", "F1-D01"],
          distance_m: 76,
          polyline: [[0, 50], [15, 50], [58, 74]],
        }}
      />,
    );

    const slot = screen.getByRole("button", { name: /F1-D01, Zone D/ });
    expect(slot.getAttribute("data-x")).toBe("58");
    expect(slot.getAttribute("data-y")).toBe("74");
    expect(screen.getByTestId("route-polyline").getAttribute("points")).toBe(
      "0,50 15,50 58,74",
    );
  });
});

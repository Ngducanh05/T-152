import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type {
  ParkingMap as ParkingMapData,
} from "@/lib/types";
import { getDisplayPoint } from "@/lib/map-geometry";
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

    const { container } = render(
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

    expect(screen.getAllByRole("button", { name: /Ô đỗ/ })).toHaveLength(40);
    expect(screen.getByRole("button", { name: /F1-D10, Khu D/ })).toBeDefined();
    expect(screen.getByRole("button", { name: /F1-A01.*Đã giữ.*Chỗ đã giữ/ }).getAttribute("data-status")).toBe("RESERVED");
    expect(screen.getByRole("button", { name: /F1-D01.*Có sạc điện.*Được đề xuất/ })).toBeDefined();
    expect(screen.getByTestId("current-location")).toBeDefined();
    expect(container.querySelector('[data-node-id="F1-CP1"] circle')?.getAttribute("r")).toBe("0.85");
    expect(getDisplayPoint({ id: "F1-ELEVATOR", floor_id: "F1", type: "ELEVATOR", x: 50, y: 92 })).toEqual([50, 96]);
    expect(container.querySelector(".elevator-road")?.getAttribute("d")).toBe("M 50 50 L 50 90");
  });

  it("lays slots out as usable bays and routes along orthogonal driving lanes", () => {
    const { map, slots, status } = fixture();

    render(
      <ParkingMap
        map={map}
        slots={slots}
        status={status}
        route={{
          path: ["F1-ENTRANCE", "F1-CP1", "F1-D-W", "F1-D01"],
          distance_m: 76,
          polyline: [[0, 50], [15, 50], [58, 70], [58, 74]],
        }}
      />,
    );

    const slot = screen.getByRole("button", { name: /F1-D01, Khu D/ });
    expect(slot.getAttribute("data-x")).toBe("55");
    expect(slot.getAttribute("data-y")).toBe("61");
    expect(screen.getByTestId("route-polyline").getAttribute("points")).toBe(
      "0,50 15,50 50,50 55,50 55,61",
    );
  });
});

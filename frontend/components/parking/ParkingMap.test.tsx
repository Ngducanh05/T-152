import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type {
  MapEdge,
  MapNode,
  ParkingMap as ParkingMapData,
  ParkingSlot,
  ParkingStatus,
  ZoneId,
} from "@/lib/types";

import { ParkingMap } from "./ParkingMap";

const zones: ZoneId[] = ["A", "B", "C", "D"];

afterEach(cleanup);

function fixture() {
  const slots: ParkingSlot[] = [];
  const nodes: MapNode[] = [
    { id: "F1-CP1", floor_id: "F1", type: "CHECKPOINT", x: 15, y: 50 },
  ];
  const edges: MapEdge[] = [];

  for (const zoneId of zones) {
    const north = zoneId === "A" || zoneId === "B";
    const westX = zoneId === "A" || zoneId === "C" ? 25 : 58;
    const aisleId = `F1-${zoneId}-W`;
    nodes.push({
      id: aisleId,
      floor_id: "F1",
      type: "AISLE",
      x: westX,
      y: north ? 30 : 70,
    });
    for (let index = 1; index <= 10; index += 1) {
      const id = `F1-${zoneId}${String(index).padStart(2, "0")}`;
      const status =
        id === "F1-A01" ? "RESERVED" : id === "F1-B01" ? "OCCUPIED" : "AVAILABLE";
      slots.push({
        id,
        floor_id: "F1",
        zone_id: zoneId,
        node_id: aisleId,
        status,
        has_charger: (zoneId === "C" || zoneId === "D") && index <= 5,
        is_accessible: id === "F1-D10",
        version: 0,
        occupied_by_vehicle_id: null,
      });
      nodes.push({
        id,
        floor_id: "F1",
        type: "SLOT",
        x: westX + ((index - 1) % 5) * 4.25,
        y: north ? (index <= 5 ? 22 : 26) : index <= 5 ? 74 : 78,
      });
      edges.push({
        from_node: aisleId,
        to_node: id,
        distance_m: 4,
        bidirectional: true,
        enabled: true,
      });
    }
  }

  const map: ParkingMapData = { nodes, edges, slots };
  const status: ParkingStatus = {
    total: 40,
    available: 38,
    reserved: 1,
    occupied: 1,
    by_zone: {
      A: { AVAILABLE: 9, RESERVED: 1, OCCUPIED: 0 },
      B: { AVAILABLE: 9, RESERVED: 0, OCCUPIED: 1 },
      C: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
      D: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
    },
  };
  return { map, slots, status };
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

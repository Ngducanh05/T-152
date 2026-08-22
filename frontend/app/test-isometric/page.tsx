"use client";

import { notFound } from "next/navigation";
import { useMemo, useState } from "react";

import { ParkingMap } from "@/components/parking/ParkingMap";
import type {
  MapEdge,
  MapNode,
  ParkingMap as ParkingMapType,
  ParkingSlot,
  ParkingStatus,
  RouteResult,
  SlotStatus,
  ZoneId,
} from "@/lib/types";

function buildTestMap(): { map: ParkingMapType; slots: ParkingSlot[] } {
  const zones: ZoneId[] = ["A", "B", "C", "D"];
  const nodes: MapNode[] = [
    { id: "F1-ENTRANCE", floor_id: "F1", type: "ENTRANCE", x: 0, y: 50 },
    { id: "F1-CP1", floor_id: "F1", type: "CHECKPOINT", x: 15, y: 50 },
  ];
  const edges: MapEdge[] = [
    {
      from_node: "F1-ENTRANCE",
      to_node: "F1-CP1",
      distance_m: 15,
      bidirectional: true,
      enabled: true,
      allowed_mode: null,
    },
  ];
  const slots: ParkingSlot[] = [];

  for (const zoneId of zones) {
    const north = zoneId === "A" || zoneId === "B";
    const aisleX = zoneId === "A" || zoneId === "C" ? 25 : 58;
    const aisleId = `F1-${zoneId}-W`;
    nodes.push({
      id: aisleId,
      floor_id: "F1",
      type: "AISLE",
      x: aisleX,
      y: north ? 30 : 70,
    });
    edges.push({
      from_node: "F1-CP1",
      to_node: aisleId,
      distance_m: 20,
      bidirectional: true,
      enabled: true,
      allowed_mode: null,
    });

    for (let index = 1; index <= 10; index += 1) {
      const id = `F1-${zoneId}${String(index).padStart(2, "0")}`;
      const status: SlotStatus =
        id === "F1-A01"
          ? "RESERVED"
          : id === "F1-B01"
            ? "OCCUPIED"
            : "AVAILABLE";
      slots.push({
        id,
        floor_id: "F1",
        zone_id: zoneId,
        node_id: aisleId,
        status,
        has_charger: (zoneId === "C" || zoneId === "D") && index <= 5,
        is_accessible: id === "F1-D10",
        version: status === "AVAILABLE" ? 7 : 8,
        occupied_by_vehicle_id:
          status === "OCCUPIED" ? "VEHICLE-001" : null,
      });
      nodes.push({
        id,
        floor_id: "F1",
        type: "SLOT",
        x: aisleX + ((index - 1) % 5) * 4.25,
        y: north ? (index <= 5 ? 22 : 26) : index <= 5 ? 74 : 78,
      });
      edges.push({
        from_node: aisleId,
        to_node: id,
        distance_m: 4,
        bidirectional: true,
        enabled: true,
        allowed_mode: null,
      });
    }
  }

  // Thêm các node và edge cho F2
  const f2Nodes: MapNode[] = [
    { id: "F2-RAMP", floor_id: "F2", type: "RAMP", x: 85, y: 75 },
    { id: "F2-CP3", floor_id: "F2", type: "CHECKPOINT", x: 85, y: 50 },
    { id: "F2-D-W", floor_id: "F2", type: "AISLE", x: 58, y: 70 },
    { id: "F2-D01", floor_id: "F2", type: "SLOT", x: 58, y: 74 },
  ];
  const f2Edges: MapEdge[] = [
    {
      from_node: "F2-RAMP",
      to_node: "F2-CP3",
      distance_m: 25,
      bidirectional: true,
      enabled: true,
      allowed_mode: null,
    },
    {
      from_node: "F2-CP3",
      to_node: "F2-D-W",
      distance_m: 22,
      bidirectional: true,
      enabled: true,
      allowed_mode: null,
    },
    {
      from_node: "F2-D-W",
      to_node: "F2-D01",
      distance_m: 4,
      bidirectional: true,
      enabled: true,
      allowed_mode: null,
    },
  ];
  const f2Slots: ParkingSlot[] = [
    {
      id: "F2-D01",
      floor_id: "F2",
      zone_id: "D",
      node_id: "F2-D-W",
      status: "AVAILABLE",
      has_charger: false,
      is_accessible: false,
      version: 1,
      occupied_by_vehicle_id: null,
    },
  ];

  return {
    map: {
      nodes: [...nodes, ...f2Nodes],
      edges: [...edges, ...f2Edges],
      slots: [...slots, ...f2Slots],
    },
    slots: [...slots, ...f2Slots],
  };
}

const statusFixture: ParkingStatus = {
  total: 41,
  available: 39,
  reserved: 1,
  occupied: 1,
  by_zone: {
    A: { AVAILABLE: 9, RESERVED: 1, OCCUPIED: 0 },
    B: { AVAILABLE: 9, RESERVED: 0, OCCUPIED: 1 },
    C: { AVAILABLE: 10, RESERVED: 0, OCCUPIED: 0 },
    D: { AVAILABLE: 11, RESERVED: 0, OCCUPIED: 0 },
  },
};

const multiFloorRoute: RouteResult = {
  path: [
    "F1-ENTRANCE",
    "F1-CP1",
    "F1-D-W",
    "F1-D01",
    "F2-RAMP",
    "F2-CP3",
    "F2-D-W",
    "F2-D01",
  ],
  distance_m: 150,
  polyline: [
    [0, 50],
    [15, 50],
    [58, 70],
    [58, 74],
    [85, 75],
    [85, 50],
    [58, 70],
    [58, 74],
  ],
};

export default function TestIsometricHarness() {
  if (
    process.env.NODE_ENV === "production" &&
    process.env.NEXT_PUBLIC_ENABLE_TEST_HARNESS !== "true"
  ) {
    notFound();
  }

  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null);
  const { map, slots } = useMemo(() => buildTestMap(), []);

  return (
    <main style={{ padding: 20 }}>
      <h1>Bản đồ kiểm thử Isometric</h1>
      <ParkingMap
        map={map}
        slots={slots}
        status={statusFixture}
        currentLocationNodeId="F1-A01"
        route={multiFloorRoute}
        selectedSlotId={selectedSlotId}
        onSelectSlot={setSelectedSlotId}
      />
    </main>
  );
}

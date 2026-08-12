import { useMemo } from "react";

import type {
  FloorScopedId,
  ParkingMap as ParkingMapData,
  ParkingSlot as ParkingSlotData,
  ParkingStatus,
  RouteResult,
  ZoneId,
} from "@/lib/types";

import { ParkingSlot } from "./ParkingSlot";
import { ParkingSummary } from "./ParkingSummary";
import { RouteOverlay } from "./RouteOverlay";
import { StatusLegend } from "./StatusLegend";

export interface ParkingMapProps {
  map: ParkingMapData;
  slots: ParkingSlotData[];
  status: ParkingStatus;
  recommendedSlotIds?: FloorScopedId[];
  selectedSlotId?: FloorScopedId | null;
  activeReservationSlotId?: FloorScopedId | null;
  parkedVehicleSlotId?: FloorScopedId | null;
  currentLocationNodeId?: FloorScopedId | null;
  route?: RouteResult | null;
  onSelectSlot?: (slotId: string) => void;
}

export function ParkingMap({
  map,
  slots,
  status,
  recommendedSlotIds = [],
  selectedSlotId = null,
  activeReservationSlotId = null,
  parkedVehicleSlotId = null,
  currentLocationNodeId = null,
  route = null,
  onSelectSlot,
}: ParkingMapProps) {
  const nodeById = useMemo(
    () => new Map(map.nodes.map((node) => [node.id, node])),
    [map.nodes],
  );
  const recommended = useMemo(
    () => new Set(recommendedSlotIds),
    [recommendedSlotIds],
  );
  const currentNode = currentLocationNodeId
    ? nodeById.get(currentLocationNodeId)
    : undefined;
  const zoneLabels = (["A", "B", "C", "D"] as ZoneId[]).map((zoneId) => {
    const zoneNodes = slots
      .filter((slot) => slot.zone_id === zoneId)
      .map((slot) => nodeById.get(slot.id))
      .filter((node) => node !== undefined);
    return {
      zoneId,
      x: zoneNodes.reduce((sum, node) => sum + node.x, 0) / zoneNodes.length,
      y: Math.min(...zoneNodes.map((node) => node.y)) - 4,
    };
  });

  return (
    <section className="card map-card" aria-labelledby="parking-map-heading">
      <div className="card-header">
        <div>
          <h2 id="parking-map-heading">Sơ đồ bãi xe trực tiếp</h2>
          <p>Canonical F1 map · cập nhật trạng thái mỗi 2 giây</p>
        </div>
        <span className="live-map-indicator"><i />Live</span>
      </div>
      <ParkingSummary status={status} slots={slots} />
      <div className="parking-map api-parking-map" data-testid="parking-map">
        <div className="map-viewport">
          <svg
            className="map-network"
            viewBox="0 0 100 100"
            role="img"
            aria-label="Parking graph with enabled edges and current route"
            preserveAspectRatio="none"
          >
          <g className="map-edges" aria-label="Enabled parking map edges">
            {map.edges.filter((edge) => edge.enabled).map((edge) => {
              const from = nodeById.get(edge.from_node);
              const to = nodeById.get(edge.to_node);
              if (!from || !to) return null;
              return (
                <line
                  key={`${edge.from_node}:${edge.to_node}`}
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  data-edge={`${edge.from_node}:${edge.to_node}`}
                />
              );
            })}
          </g>
          <g className="map-core-nodes" aria-label="Parking map nodes">
            {map.nodes.filter((node) => node.type !== "SLOT").map((node) => (
              <g key={node.id} data-node-id={node.id}>
                <circle cx={node.x} cy={node.y} r={node.type === "AISLE" ? 0.8 : 1.5} />
                {node.type !== "AISLE" && (
                  <text x={node.x} y={node.y - 2.5} textAnchor="middle">
                    {node.id.replace("F1-", "")}
                  </text>
                )}
              </g>
            ))}
          </g>
          <g className="map-zone-labels" aria-hidden="true">
            {zoneLabels.map((zone) => (
              <text key={zone.zoneId} x={zone.x} y={zone.y} textAnchor="middle">
                KHU {zone.zoneId}
              </text>
            ))}
          </g>
          <RouteOverlay route={route} />
          {currentNode && currentNode.type !== "SLOT" && (
            <g
              className="current-location-node"
              transform={`translate(${currentNode.x} ${currentNode.y})`}
              data-testid="current-location"
              aria-label={`Current user location ${currentNode.id}`}
            >
              <circle r="3.2" />
              <text textAnchor="middle" y="1.1">⌖</text>
            </g>
          )}
          </svg>
          <div className="map-slot-layer" aria-label="Parking slots">
            {slots.map((slot) => {
              // A slot's own MapNode is its display coordinate. node_id is only
              // the connected aisle and must never be used for positioning.
              const displayNode = nodeById.get(slot.id);
              if (!displayNode) return null;
              return (
                <ParkingSlot
                  key={slot.id}
                  slot={slot}
                  displayNode={displayNode}
                  recommended={recommended.has(slot.id)}
                  selected={selectedSlotId === slot.id}
                  activeReservation={activeReservationSlotId === slot.id}
                  parkedVehicle={parkedVehicleSlotId === slot.id}
                  currentLocation={currentLocationNodeId === slot.id}
                  onSelect={onSelectSlot}
                />
              );
            })}
          </div>
        </div>
      </div>
      <StatusLegend />
    </section>
  );
}

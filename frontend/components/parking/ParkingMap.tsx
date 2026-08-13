import { useMemo } from "react";

import {
  buildLaneSegment,
  getDisplayPoint,
  pointsToPath,
} from "@/lib/map-geometry";
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
      y: zoneId === "A" || zoneId === "B" ? 10 : 55,
    };
  });
  const enabledEdges = map.edges
    .filter((edge) => edge.enabled)
    .map((edge) => {
      const from = nodeById.get(edge.from_node);
      const to = nodeById.get(edge.to_node);
      if (!from || !to) return null;
      const points = buildLaneSegment(from, to);
      const isSlotConnector = from.type === "SLOT" || to.type === "SLOT";
      const connectorPoints = from.type === "SLOT"
        ? points.slice(0, 2)
        : points.slice(-2);
      return {
        ...edge,
        from,
        to,
        d: pointsToPath(points),
        displayD: pointsToPath(isSlotConnector ? connectorPoints : points),
        isSlotConnector,
        isPedestrian: from.type === "ELEVATOR" || to.type === "ELEVATOR",
      };
    })
    .filter((edge) => edge !== null);

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
          <g className="map-zone-surfaces" aria-hidden="true">
            <rect x="22" y="9" width="26" height="39" rx="2" />
            <rect x="52" y="9" width="26" height="39" rx="2" />
            <rect x="22" y="52" width="26" height="36" rx="2" />
            <rect x="52" y="52" width="26" height="36" rx="2" />
          </g>
          <g className="map-road-surfaces" aria-hidden="true">
            <path className="main-road" d="M 0 50 L 100 50" />
            <path className="zone-ring" d="M 20 50 L 20 7 L 80 7 L 80 50" />
            <path className="shared-road" d="M 50 7 L 50 50" />
            <path className="zone-ring" d="M 20 50 L 20 90 L 80 90 L 80 50" />
            <path className="shared-road elevator-road" d="M 50 50 L 50 90" />
          </g>
          <g className="map-shared-road-markings" aria-hidden="true">
            <path d="M 0 50 L 100 50" />
            <path d="M 20 50 L 20 7 L 80 7 L 80 50" />
            <path d="M 50 7 L 50 50" />
            <path d="M 20 50 L 20 90 L 80 90 L 80 50" />
            <path d="M 50 50 L 50 90" />
          </g>
          <g className="map-edges" aria-label="Enabled parking map lanes">
            {enabledEdges.map((edge) => (
              <path
                key={`${edge.from_node}:${edge.to_node}`}
                d={edge.displayD}
                className={`${edge.isSlotConnector ? "slot-connector" : "road-centreline"} ${edge.isPedestrian ? "pedestrian-path" : ""}`}
                data-edge={`${edge.from_node}:${edge.to_node}`}
              />
            ))}
          </g>
          <g className="map-core-nodes" aria-label="Parking map nodes">
            {map.nodes.filter((node) => node.type !== "SLOT").map((node) => {
              const [x, y] = getDisplayPoint(node);
              const radius = node.type === "AISLE" ? 0.55 : node.type === "CHECKPOINT" ? 0.85 : 1.35;
              return (
                <g key={node.id} data-node-id={node.id}>
                  <circle cx={x} cy={y} r={radius} />
                  {node.type !== "AISLE" && (
                    <text x={x} y={y - 2.3} textAnchor="middle">
                      {node.id.replace("F1-", "")}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
          <g className="map-zone-labels" aria-hidden="true">
            {zoneLabels.map((zone) => (
              <text key={zone.zoneId} x={zone.x} y={zone.y} textAnchor="middle">
                KHU {zone.zoneId}
              </text>
            ))}
          </g>
          <RouteOverlay route={route} nodeById={nodeById} />
          {currentNode && currentNode.type !== "SLOT" && (
            <g
              className="current-location-node"
              transform={`translate(${getDisplayPoint(currentNode).join(" ")})`}
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

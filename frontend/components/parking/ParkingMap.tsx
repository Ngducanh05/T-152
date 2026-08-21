import { useMemo, useState } from "react";

import {
  buildLaneSegment,
  getDisplayPoint,
  pointsToPath,
} from "@/lib/map-geometry";
import { formatFloorName } from "@/lib/parking-display";
import type {
  FloorId,
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

const FLOOR_IDS: FloorId[] = ["F1", "F2", "F3"];

const MAP_NODE_LABELS = {
  ENTRANCE: "LỐI VÀO",
  EXIT: "LỐI RA",
} as const;

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
  openReportCountBySlot?: Record<string, number>;
  onOpenReportedSlot?: (slotId: string) => void;
  heading?: string;
  description?: string;
  showSummary?: boolean;
}

function floorOfId(id: string): FloorId | null {
  const m = /^(F[1-3])-/.exec(id);
  return m ? (m[1] as FloorId) : null;
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
  openReportCountBySlot = {},
  onOpenReportedSlot,
  heading = "Sơ đồ bãi xe",
  description = "Trạng thái các ô được cập nhật tự động",
  showSummary = true,
}: ParkingMapProps) {
  // Determine initial floor from context (current location or selected slot)
  const initialFloor = useMemo<FloorId>(() => {
    if (currentLocationNodeId) {
      const f = floorOfId(currentLocationNodeId);
      if (f) return f;
    }
    if (selectedSlotId) {
      const f = floorOfId(selectedSlotId);
      if (f) return f;
    }
    return "F1";
  }, [currentLocationNodeId, selectedSlotId]);

  const [activeFloor, setActiveFloor] = useState<FloorId>(initialFloor);

  // Filter data to the active floor
  const floorNodes = useMemo(
    () => map.nodes.filter((node) => node.floor_id === activeFloor),
    [map.nodes, activeFloor],
  );
  const floorEdges = useMemo(
    () =>
      map.edges.filter((edge) => {
        const fromFloor = floorOfId(edge.from_node);
        const toFloor = floorOfId(edge.to_node);
        return fromFloor === activeFloor && toFloor === activeFloor;
      }),
    [map.edges, activeFloor],
  );
  const floorSlots = useMemo(
    () => slots.filter((slot) => slot.floor_id === activeFloor),
    [slots, activeFloor],
  );

  // Per-floor slot count for tab badges
  const floorSlotCounts = useMemo(() => {
    const counts: Record<FloorId, { available: number; total: number }> = {
      F1: { available: 0, total: 0 },
      F2: { available: 0, total: 0 },
      F3: { available: 0, total: 0 },
    };
    for (const slot of slots) {
      const fid = slot.floor_id as FloorId;
      if (counts[fid]) {
        counts[fid].total++;
        if (slot.status === "AVAILABLE") counts[fid].available++;
      }
    }
    return counts;
  }, [slots]);

  const nodeById = useMemo(
    () => new Map(floorNodes.map((node) => [node.id, node])),
    [floorNodes],
  );
  const recommended = useMemo(
    () => new Set(recommendedSlotIds),
    [recommendedSlotIds],
  );
  const currentNode = currentLocationNodeId
    ? nodeById.get(currentLocationNodeId)
    : undefined;
  const zoneLabels = (["A", "B", "C", "D"] as ZoneId[]).flatMap((zoneId) => {
    const zoneNodes = floorSlots
      .filter((slot) => slot.zone_id === zoneId)
      .map((slot) => nodeById.get(slot.id))
      .filter((node) => node !== undefined);
    if (zoneNodes.length === 0) return [];
    return [{
      zoneId,
      x: zoneNodes.reduce((sum, node) => sum + node.x, 0) / zoneNodes.length,
      y: zoneId === "A" || zoneId === "B" ? 10 : 55,
    }];
  });
  const enabledEdges = floorEdges
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
        isRamp: from.type === "RAMP" || to.type === "RAMP",
      };
    })
    .filter((edge) => edge !== null);

  // Check if any floor has ramp/elevator (for showing inter-floor indicators)
  const hasRamp = floorNodes.some((n) => n.type === "RAMP");
  const hasElevator = floorNodes.some((n) => n.type === "ELEVATOR");
  const rampLabel = activeFloor === "F2"
    ? "↕ LỐI LÊN/XUỐNG TẦNG"
    : activeFloor === "F3"
      ? "↑ LỐI LÊN TẦNG"
      : "↓ LỐI XUỐNG TẦNG";
  const rampAriaLabel = activeFloor === "F2"
    ? "Lối lên và xuống tầng"
    : activeFloor === "F3"
      ? "Lối lên tầng"
      : "Lối xuống tầng";

  return (
    <section className="card map-card" aria-labelledby="parking-map-heading">
      <div className="card-header">
        <div>
          <h2 id="parking-map-heading">{heading}</h2>
          <p>{description}</p>
        </div>
        <span className="live-map-indicator"><i />Đang cập nhật</span>
      </div>

      {/* Floor selector tabs */}
      <nav className="floor-tabs" aria-label="Chọn tầng">
        {FLOOR_IDS.map((floorId) => {
          const counts = floorSlotCounts[floorId];
          return (
            <button
              key={floorId}
              type="button"
              className={`floor-tab ${activeFloor === floorId ? "floor-tab--active" : ""}`}
              onClick={() => setActiveFloor(floorId)}
              aria-pressed={activeFloor === floorId}
              aria-label={`${formatFloorName(floorId)}: ${counts.available}/${counts.total} trống`}
            >
              <strong>{formatFloorName(floorId)}</strong>
              <span className="floor-tab-badge">
                Trống {counts.available}/{counts.total}
              </span>
            </button>
          );
        })}
      </nav>

      {showSummary && <ParkingSummary status={status} slots={floorSlots} />}
      <div className="parking-map api-parking-map" data-testid="parking-map">
        <div className="map-viewport">
          <svg
            className="map-network"
            viewBox="0 0 100 100"
            role="img"
            aria-label={`Sơ đồ ${formatFloorName(activeFloor)}`}
            preserveAspectRatio="none"
          >
          <g className="map-zone-surfaces" aria-hidden="true">
            <rect x="22" y="9" width="26" height="39" rx="2" />
            <rect x="52" y="9" width="26" height="39" rx="2" />
            <rect x="22" y="52" width="26" height="36" rx="2" />
            <rect x="52" y="52" width="26" height="36" rx="2" />
          </g>
          <g className="map-road-surfaces" aria-hidden="true">
            {activeFloor === "F1" && (
              <path className="main-road" d="M 0 50 L 100 50" />
            )}
            {activeFloor !== "F1" && (
              <path className="main-road" d="M 15 50 L 85 50" />
            )}
            <path className="zone-ring" d="M 20 50 L 20 7 L 80 7 L 80 50" />
            <path className="shared-road" d="M 50 7 L 50 50" />
            <path className="zone-ring" d="M 20 50 L 20 90 L 80 90 L 80 50" />
            <path className="shared-road elevator-road" d="M 50 50 L 50 90" />
          </g>
          <g className="map-shared-road-markings" aria-hidden="true">
            {activeFloor === "F1" && (
              <path d="M 0 50 L 100 50" />
            )}
            {activeFloor !== "F1" && (
              <path d="M 15 50 L 85 50" />
            )}
            <path d="M 20 50 L 20 7 L 80 7 L 80 50" />
            <path d="M 50 7 L 50 50" />
            <path d="M 20 50 L 20 90 L 80 90 L 80 50" />
            <path d="M 50 50 L 50 90" />
          </g>
          <g className="map-edges" aria-label="Các lối đi đang hoạt động">
            {enabledEdges.map((edge) => (
              <path
                key={`${edge.from_node}:${edge.to_node}`}
                d={edge.displayD}
                className={`${edge.isSlotConnector ? "slot-connector" : "road-centreline"} ${edge.isPedestrian ? "pedestrian-path" : ""} ${edge.isRamp ? "ramp-path" : ""}`}
                data-edge={`${edge.from_node}:${edge.to_node}`}
              />
            ))}
          </g>
          <g className="map-core-nodes" aria-label="Các điểm trên sơ đồ bãi xe">
            {floorNodes.filter((node) => node.type !== "SLOT").map((node) => {
              const [x, y] = getDisplayPoint(node);
              const radius = node.type === "AISLE" ? 0.55
                : node.type === "CHECKPOINT" ? 0.85
                : node.type === "RAMP" ? 1.35
                : 1.35;
              const isGate = node.type === "ENTRANCE" || node.type === "EXIT";
              const labelX = node.type === "ENTRANCE"
                ? 4.5
                : node.type === "EXIT"
                  ? 95.5
                  : x;
              const label = isGate
                ? MAP_NODE_LABELS[node.type]
                : node.id.replace(/^F[1-3]-/, "");
              const showLabel = node.type !== "AISLE"
                && node.type !== "RAMP"
                && node.type !== "ELEVATOR";
              return (
                <g key={node.id} data-node-id={node.id}>
                  <circle cx={x} cy={y} r={radius} className={node.type === "RAMP" ? "ramp-node" : ""} />
                  {showLabel && (
                    <text
                      x={labelX}
                      y={y - 2.3}
                      textAnchor="middle"
                      className={isGate ? "map-gate-label" : undefined}
                    >
                      {label}
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
          {/* Inter-floor connection indicators */}
          {hasRamp && (
            <g className="map-interfloor-indicator map-ramp-indicator" aria-label={rampAriaLabel}>
              <rect x="76" y="67" width="22" height="5.5" rx="2.75" />
              <text x="87" y="70.65" textAnchor="middle" className="interfloor-label">{rampLabel}</text>
            </g>
          )}
          {hasElevator && (
            <g className="map-interfloor-indicator map-elevator-indicator" aria-label="Thang máy liên tầng">
              <rect x="42.5" y="91" width="15" height="5.5" rx="2.75" />
              <text x="50" y="94.65" textAnchor="middle" className="interfloor-label">↕ THANG MÁY</text>
            </g>
          )}
          <RouteOverlay route={route} nodeById={nodeById} />
          {currentNode && currentNode.type !== "SLOT" && (
            <g
              className="current-location-node"
              transform={`translate(${getDisplayPoint(currentNode).join(" ")})`}
              data-testid="current-location"
              aria-label={`Vị trí hiện tại ${currentNode.id}`}
            >
              <circle r="3.2" />
              <text textAnchor="middle" y="1.1">⌖</text>
            </g>
          )}
          </svg>
          <div className="map-slot-layer" aria-label="Các ô đỗ xe">
            {floorSlots.map((slot) => {
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
                  openReportCount={openReportCountBySlot[slot.id] ?? 0}
                  onSelect={onSelectSlot}
                  onOpenReportedSlot={onOpenReportedSlot}
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

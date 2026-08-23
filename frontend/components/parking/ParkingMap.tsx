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
  MapEdge,
  MapNode,
  ParkingMap as ParkingMapData,
  ParkingSlot as ParkingSlotData,
  ParkingStatus,
  RouteResult,
  ZoneId,
} from "@/lib/types";

import { IsometricMap } from "./IsometricMap";
import { ParkingSlot } from "./ParkingSlot";
import { ParkingSummary } from "./ParkingSummary";
import { RouteOverlay } from "./RouteOverlay";
import { StatusLegend } from "./StatusLegend";

const FLOOR_IDS: FloorId[] = ["F1", "F2", "F3"];

const MAP_NODE_LABELS: Record<string, string> = {
  ENTRANCE: "LỐI VÀO",
  EXIT: "LỐI RA",
};

export type MapViewMode = "flat" | "iso";

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
  pendingObservationCountBySlot?: Record<string, number>;
  onOpenReportedSlot?: (slotId: string) => void;
  onOpenObservedSlot?: (slotId: string) => void;
  heading?: string;
  description?: string;
  showSummary?: boolean;
  defaultViewMode?: MapViewMode;
}

function floorOfId(id: string): FloorId | null {
  const m = /^(F[1-3])-/.exec(id);
  return m ? (m[1] as FloorId) : null;
}

function cloneIdToFloor(id: string, floorId: FloorId) {
  return id.replace(/^F1-/, `${floorId}-`);
}

function completeFloorNodes(nodes: MapNode[], floorId: FloorId): MapNode[] {
  const existing = nodes.filter((node) => node.floor_id === floorId);
  if (floorId === "F1") return existing;
  const ids = new Set(existing.map((node) => node.id));
  const fallbacks = nodes
    .filter(
      (node) =>
        node.floor_id === "F1" &&
        node.type !== "ENTRANCE" &&
        node.type !== "EXIT",
    )
    .map((node) => ({
      ...node,
      id: cloneIdToFloor(node.id, floorId) as FloorScopedId,
      floor_id: floorId,
    }))
    .filter((node) => !ids.has(node.id));
  return [...existing, ...fallbacks];
}

function completeFloorEdges(edges: MapEdge[], floorId: FloorId): MapEdge[] {
  const existing = edges.filter(
    (edge) =>
      floorOfId(edge.from_node) === floorId &&
      floorOfId(edge.to_node) === floorId,
  );
  if (floorId === "F1") return existing;
  const keys = new Set(
    existing.map((edge) => `${edge.from_node}:${edge.to_node}`),
  );
  const fallbacks = edges
    .filter(
      (edge) =>
        floorOfId(edge.from_node) === "F1" &&
        floorOfId(edge.to_node) === "F1",
    )
    .map((edge) => ({
      ...edge,
      from_node: cloneIdToFloor(edge.from_node, floorId) as FloorScopedId,
      to_node: cloneIdToFloor(edge.to_node, floorId) as FloorScopedId,
    }))
    .filter((edge) => !keys.has(`${edge.from_node}:${edge.to_node}`));
  return [...existing, ...fallbacks];
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
  pendingObservationCountBySlot = {},
  onOpenReportedSlot,
  onOpenObservedSlot,
  heading = "Sơ đồ bãi xe",
  description = "Trạng thái các ô được cập nhật tự động",
  showSummary = true,
  defaultViewMode = "flat",
}: ParkingMapProps) {
  const [viewMode, setViewMode] = useState<MapViewMode>(defaultViewMode);

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

  const [floorChoice, setFloorChoice] = useState<{
    floor: FloorId;
    selectedSlotId: FloorScopedId | null;
  }>(() => ({ floor: initialFloor, selectedSlotId }));
  const newlySelectedFloor = selectedSlotId ? floorOfId(selectedSlotId) : null;
  const activeFloor =
    selectedSlotId !== floorChoice.selectedSlotId && newlySelectedFloor
      ? newlySelectedFloor
      : floorChoice.floor;

  // Filter data to the active floor
  const floorNodes = useMemo(() => {
    const base = completeFloorNodes(map.nodes, activeFloor);
    if (activeFloor === "F2") {
      // F2 có 2 dốc: lên F1 [85, 75] và xuống F3 [15, 25]
      return [
        ...base,
        { id: "F2-RAMP-DOWN", floor_id: "F2" as FloorId, type: "RAMP" as const, x: 15, y: 25 },
      ];
    }
    if (activeFloor === "F3") {
      // F3 chỉ có dốc lên F2 ở [15, 25], không có dốc ở [85, 75]
      return base.map((node) =>
        node.type === "RAMP" ? { ...node, x: 15, y: 25 } : node,
      );
    }
    return base;
  }, [map.nodes, activeFloor]);

  const floorEdges = useMemo(() => {
    const base = completeFloorEdges(map.edges, activeFloor);

    if (activeFloor === "F2") {
      // Thêm edge từ CP1 sang RAMP-DOWN cho F2
      return [
        ...base,
        {
          from_node: "F2-CP1",
          to_node: "F2-RAMP-DOWN",
          distance_m: 25,
          bidirectional: true,
          enabled: true,
          allowed_mode: "VEHICLE" as const,
        },
      ];
    }

    if (activeFloor === "F3") {
      // Thay edge nối tới [85, 75] bằng edge nối từ CP1 tới F3-RAMP ở [15, 25]
      return base.map((edge) => {
        const isRampEdge =
          edge.from_node.includes("RAMP") || edge.to_node.includes("RAMP");
        if (!isRampEdge) return edge;
        return {
          ...edge,
          from_node: "F3-CP1",
          to_node: "F3-RAMP",
        };
      });
    }

    return base;
  }, [map.edges, activeFloor]);
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

  const floorRoute = useMemo<RouteResult | null>(() => {
    if (!route || !route.path.length) return null;

    // 1. Tìm các dải index liên tục trong route.path có node thuộc tầng đang xem
    const ranges: { start: number; end: number; len: number }[] = [];
    let currentStart = -1;

    for (let i = 0; i < route.path.length; i += 1) {
      if (nodeById.has(route.path[i])) {
        if (currentStart === -1) currentStart = i;
      } else if (currentStart !== -1) {
        ranges.push({
          start: currentStart,
          end: i - 1,
          len: i - currentStart,
        });
        currentStart = -1;
      }
    }
    if (currentStart !== -1) {
      ranges.push({
        start: currentStart,
        end: route.path.length - 1,
        len: route.path.length - currentStart,
      });
    }

    if (ranges.length === 0) return null;

    // 2. Chọn dải liên tục dài nhất
    ranges.sort((a, b) => b.len - a.len);
    const bestRange = ranges[0];

    // 3. Dưới 2 node thì trả null
    if (bestRange.len < 2) return null;

    // 4. Cắt path và polyline tương ứng
    const slicedPath = route.path.slice(bestRange.start, bestRange.end + 1);
    const slicedPolyline = route.polyline.slice(
      bestRange.start,
      bestRange.end + 1,
    );

    // Tính tổng distance_m từ floorEdges cho các cặp node liên tiếp trong slicedPath
    let distance_m = 0;
    for (let i = 0; i < slicedPath.length - 1; i += 1) {
      const u = slicedPath[i];
      const v = slicedPath[i + 1];
      const edge = floorEdges.find(
        (e) =>
          (e.from_node === u && e.to_node === v) ||
          (e.from_node === v && e.to_node === u),
      );
      if (edge) {
        distance_m += edge.distance_m;
      }
    }

    return {
      path: slicedPath,
      polyline: slicedPolyline,
      distance_m,
    };
  }, [route, nodeById, floorEdges]);

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
              onClick={() => setFloorChoice({ floor: floorId, selectedSlotId })}
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

      {/* View mode selector */}
      <nav className="map-view-toggle" aria-label="Kiểu hiển thị sơ đồ">
        <button
          type="button"
          onClick={() => setViewMode("flat")}
          aria-pressed={viewMode === "flat"}
        >
          Sơ đồ phẳng
        </button>
        <button
          type="button"
          onClick={() => setViewMode("iso")}
          aria-pressed={viewMode === "iso"}
        >
          Phối cảnh hầm
        </button>
      </nav>

      {showSummary && status && <ParkingSummary status={status} slots={floorSlots} />}

      {viewMode === "flat" ? (
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
              {floorNodes.filter((node) => node.type !== "SLOT" && node.type !== "CHECKPOINT").map((node) => {
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
              <>
                {activeFloor === "F1" && (
                  <g className="map-interfloor-indicator map-ramp-indicator" aria-label="Lối xuống F2">
                    <rect x="78" y="67" width="18" height="5.5" rx="2.75" />
                    <text x="87" y="70.65" textAnchor="middle" className="interfloor-label">
                      ↓ Xuống F2
                    </text>
                  </g>
                )}
                {activeFloor === "F2" && (
                  <g className="map-interfloor-indicator map-ramp-indicator" aria-label="Lối lên và xuống tầng">
                    {/* Dốc lên F1 tại [85, 75] */}
                    <g className="map-ramp-sub-indicator" aria-label="Lối lên F1">
                      <rect x="79" y="67" width="16" height="5.5" rx="2.75" />
                      <text x="87" y="70.65" textAnchor="middle" className="interfloor-label">
                        ↑ Lên F1
                      </text>
                    </g>
                    {/* Dốc xuống F3 tại [14, 32] */}
                    <g className="map-ramp-sub-indicator" aria-label="Lối xuống F3">
                      <rect x="5" y="29.25" width="18" height="5.5" rx="2.75" />
                      <text x="14" y="32.9" textAnchor="middle" className="interfloor-label">
                        ↓ Xuống F3
                      </text>
                    </g>
                  </g>
                )}
                {activeFloor === "F3" && (
                  <g className="map-interfloor-indicator map-ramp-indicator" aria-label="Lối lên F2">
                    {/* Dốc lên F2 tại [14, 32] */}
                    <rect x="6" y="29.25" width="16" height="5.5" rx="2.75" />
                    <text x="14" y="32.9" textAnchor="middle" className="interfloor-label">
                      ↑ Lên F2
                    </text>
                  </g>
                )}
              </>
            )}
            {hasElevator && (
              <g className="map-interfloor-indicator map-elevator-indicator" aria-label="Thang máy liên tầng">
                <rect x="42.5" y="91" width="15" height="5.5" rx="2.75" />
                <text x="50" y="94.65" textAnchor="middle" className="interfloor-label">↕ THANG MÁY</text>
              </g>
            )}
            {floorRoute && <RouteOverlay route={floorRoute} nodeById={nodeById} />}
            {currentNode && currentNode.type !== "SLOT" && currentNode.type !== "CHECKPOINT" && (
              <g
                className="current-location-node"
                transform={`translate(${getDisplayPoint(currentNode).join(" ")})`}
                data-testid="current-location"
                aria-label="Vị trí hiện tại trong bãi"
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
                    pendingObservationCount={pendingObservationCountBySlot[slot.id] ?? 0}
                    onSelect={onSelectSlot}
                    onOpenReportedSlot={onOpenReportedSlot}
                    onOpenObservedSlot={onOpenObservedSlot}
                  />
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        <div className="parking-map api-parking-map">
          <IsometricMap
            floorId={activeFloor}
            nodes={floorNodes}
            edges={floorEdges}
            slots={floorSlots}
            route={floorRoute}
            recommendedSlotIds={recommendedSlotIds}
            selectedSlotId={selectedSlotId}
            activeReservationSlotId={activeReservationSlotId}
            parkedVehicleSlotId={parkedVehicleSlotId}
            currentLocationNodeId={currentLocationNodeId}
            openReportCountBySlot={openReportCountBySlot}
            pendingObservationCountBySlot={pendingObservationCountBySlot}
            onSelectSlot={onSelectSlot}
            onOpenReportedSlot={onOpenReportedSlot}
            onOpenObservedSlot={onOpenObservedSlot}
          />
        </div>
      )}
      <StatusLegend />
    </section>
  );
}

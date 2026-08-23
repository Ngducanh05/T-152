import React, { useMemo } from "react";

import { pointsToPolygon } from "@/lib/iso-geometry";
import { buildIsoScene } from "@/lib/iso-scene";
import type { IsoBay, IsoProp } from "@/lib/iso-scene";
import { formatFloorName } from "@/lib/parking-display";
import type {
  FloorId,
  FloorScopedId,
  MapEdge,
  MapNode,
  ParkingSlot as ParkingSlotData,
  RouteResult,
} from "@/lib/types";

import { ParkingSlot } from "./ParkingSlot";

export interface IsometricMapProps {
  floorId: FloorId;
  nodes: MapNode[];
  edges: MapEdge[];
  slots: ParkingSlotData[];
  route?: RouteResult | null;
  recommendedSlotIds?: FloorScopedId[];
  selectedSlotId?: FloorScopedId | null;
  activeReservationSlotId?: FloorScopedId | null;
  parkedVehicleSlotId?: FloorScopedId | null;
  currentLocationNodeId?: FloorScopedId | null;
  openReportCountBySlot?: Record<string, number>;
  pendingObservationCountBySlot?: Record<string, number>;
  onSelectSlot?: (slotId: string) => void;
  onOpenReportedSlot?: (slotId: string) => void;
  onOpenObservedSlot?: (slotId: string) => void;
}

type SceneDepthItem =
  | { type: "bay"; depth: number; bay: IsoBay }
  | { type: "prop"; depth: number; prop: IsoProp };

export function IsometricMap({
  floorId,
  nodes,
  edges,
  slots,
  route = null,
  recommendedSlotIds = [],
  selectedSlotId = null,
  activeReservationSlotId = null,
  parkedVehicleSlotId = null,
  currentLocationNodeId = null,
  openReportCountBySlot = {},
  pendingObservationCountBySlot = {},
  onSelectSlot,
  onOpenReportedSlot,
  onOpenObservedSlot,
}: IsometricMapProps): React.JSX.Element {
  const scene = useMemo(
    () =>
      buildIsoScene({
        floorId,
        nodes,
        edges,
        slots,
        route: route ?? null,
        currentLocationNodeId: currentLocationNodeId ?? null,
      }),
    [floorId, nodes, edges, slots, route, currentLocationNodeId],
  );

  const nodeById = useMemo(
    () => new Map(nodes.map((node) => [node.id, node])),
    [nodes],
  );
  const slotById = useMemo(
    () => new Map(slots.map((slot) => [slot.id, slot])),
    [slots],
  );
  const recommended = useMemo(
    () => new Set(recommendedSlotIds),
    [recommendedSlotIds],
  );

  const depthSortedItems = useMemo<SceneDepthItem[]>(() => {
    const items: SceneDepthItem[] = [
      ...scene.bays.map((bay) => ({
        type: "bay" as const,
        depth: bay.depth,
        bay,
      })),
      ...scene.props
        .filter((prop) => prop.kind !== "CHECKPOINT")
        .map((prop) => ({
          type: "prop" as const,
          depth: prop.depth,
          prop,
        })),
    ];
    items.sort((a, b) => a.depth - b.depth);
    return items;
  }, [scene.bays, scene.props]);

  return (
    <div className="map-viewport map-viewport--iso">
      {/* Background SVG Canvas: Slab, Zones, Roads, Ground Bay Outlines, Route */}
      <svg
        className="map-network map-network--iso"
        viewBox="0 0 200 140"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Phối cảnh ${formatFloorName(floorId)}`}
        data-testid="isometric-map"
      >
        <defs>
          <marker
            id="iso-route-arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="5"
            markerHeight="5"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="#3373f1" />
          </marker>
        </defs>

        {/* 1. Khối sàn (Slab) */}
        <g className="iso-slab" aria-hidden="true">
          <polygon
            className="iso-slab-left"
            points={pointsToPolygon(scene.slab.left)}
          />
          <polygon
            className="iso-slab-right"
            points={pointsToPolygon(scene.slab.right)}
          />
          <polygon
            className="iso-slab-top"
            points={pointsToPolygon(scene.slab.top)}
          />
        </g>

        {/* 2. Mặt khu A-D */}
        <g className="iso-zones" aria-hidden="true">
          {scene.zones.map((zone) => (
            <polygon
              key={zone.id}
              className="iso-zone"
              points={pointsToPolygon(zone.points)}
            />
          ))}
        </g>

        {/* 3 & 4. Đường xe chạy và vạch kẻ */}
        <g className="iso-roads" aria-hidden="true">
          {scene.roads.map((road) => (
            <g key={road.id} className={`iso-road iso-road--${road.kind}`}>
              {road.quads.map((quad, index) => (
                <polygon
                  key={index}
                  className="iso-road-surface"
                  points={pointsToPolygon(quad)}
                />
              ))}
              <polyline
                className="iso-road-marking"
                points={pointsToPolygon(road.markings)}
              />
            </g>
          ))}
        </g>

        {/* 5. Vạch khoang đỗ trên mặt sàn */}
        <g className="iso-bays-ground" aria-hidden="true">
          {scene.bays.map((bay) => (
            <polygon
              key={`bay-ground-${bay.slotId}`}
              className={`iso-bay status-${bay.status.toLowerCase()}`}
              points={pointsToPolygon(bay.footprint)}
              data-slot-id={bay.slotId}
            />
          ))}
        </g>

        {/* 8. Tuyến đường (Route) & Vị trí hiện tại */}
        {scene.routePoints && (
          <g
            className="iso-route map-route"
            aria-label="Đường đang xem"
          >
            <polyline
              className="map-route-glow"
              points={pointsToPolygon(scene.routePoints)}
              fill="none"
              aria-hidden="true"
            />
            <polyline
              className="map-route-line"
              points={pointsToPolygon(scene.routePoints)}
              fill="none"
              markerEnd="url(#iso-route-arrow)"
              data-testid="route-polyline"
            />
          </g>
        )}

        {scene.currentLocationAt && (
          <g
            className="current-location-node iso-current-location"
            transform={`translate(${scene.currentLocationAt[0]} ${scene.currentLocationAt[1]})`}
            data-testid="current-location"
            aria-label="Vị trí hiện tại"
          >
            <circle r="3.2" />
            <text textAnchor="middle" y="1.1">
              ⌖
            </text>
          </g>
        )}

        {/* 9. Nhãn chữ sàn */}
        <g className="iso-labels" aria-hidden="true">
          {scene.labels.map((label) => (
            <text
              key={label.id}
              className="iso-label"
              x={label.at[0]}
              y={label.at[1]}
              textAnchor="middle"
            >
              {label.text}
            </text>
          ))}
        </g>
      </svg>

      {/* Unified Depth-Sorted 3D Foreground & Interactive Layer */}
      <div className="map-slot-layer map-slot-layer--iso" aria-label="Các ô đỗ xe">
        {depthSortedItems.map((entry, depthIndex) => {
          if (entry.type === "bay") {
            const { bay } = entry;
            const slot = slotById.get(bay.slotId);
            const displayNode = nodeById.get(bay.slotId);
            if (!slot || !displayNode) return null;

            const carData = bay.car;

            return (
              <div
                key={`bay-layer-${bay.slotId}`}
                className="iso-depth-item"
                style={{
                  position: "absolute",
                  inset: 0,
                  zIndex: 20 + depthIndex,
                  pointerEvents: "none",
                }}
              >
                {carData && (
                  <svg
                    className="iso-depth-svg"
                    viewBox="0 0 200 140"
                    preserveAspectRatio="none"
                    aria-hidden="true"
                  >
                    <g
                      className="iso-car iso-car--box"
                      data-car-slot={bay.slotId}
                      data-car-shape="rectangular-box"
                    >
                      <polygon
                        className="iso-car-shadow"
                        points={pointsToPolygon(carData.top)}
                        transform="translate(0 0.9)"
                      />
                      <polygon
                        className="iso-car-box-left"
                        points={pointsToPolygon(carData.left)}
                      />
                      <polygon
                        className="iso-car-box-right"
                        points={pointsToPolygon(carData.right)}
                      />
                      <polygon
                        className="iso-car-box-top"
                        points={pointsToPolygon(carData.top)}
                      />
                    </g>
                  </svg>
                )}
                <ParkingSlot
                  slot={slot}
                  displayNode={displayNode}
                  position={bay.centerPercent}
                  variant="iso"
                  depthIndex={20 + depthIndex}
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
              </div>
            );
          }

          const { prop } = entry;
          return (
            <div
              key={`prop-layer-${prop.id}`}
              className="iso-depth-item"
              style={{
                position: "absolute",
                inset: 0,
                zIndex: 20 + depthIndex,
                pointerEvents: "none",
              }}
            >
              <svg
                className="iso-depth-svg"
                viewBox="0 0 200 140"
                preserveAspectRatio="none"
                aria-hidden="true"
              >
                {prop.box && (
                  <g
                    className={`iso-prop iso-prop--${prop.kind.toLowerCase()}`}
                    data-prop-id={prop.id}
                  >
                    <polygon
                      className="iso-prop-left"
                      points={pointsToPolygon(prop.box.left)}
                    />
                    <polygon
                      className="iso-prop-right"
                      points={pointsToPolygon(prop.box.right)}
                    />
                    <polygon
                      className="iso-prop-top"
                      points={pointsToPolygon(prop.box.top)}
                    />
                    {prop.kind === "ELEVATOR" && (
                      <>
                        {/* Steel Frame Pillars */}
                        <line
                          x1={prop.box.left[0][0]}
                          y1={prop.box.left[0][1]}
                          x2={prop.box.left[3][0]}
                          y2={prop.box.left[3][1]}
                          stroke="#1e293b"
                          strokeWidth="0.4"
                        />
                        <line
                          x1={prop.box.left[1][0]}
                          y1={prop.box.left[1][1]}
                          x2={prop.box.left[2][0]}
                          y2={prop.box.left[2][1]}
                          stroke="#1e293b"
                          strokeWidth="0.4"
                        />
                        <line
                          x1={prop.box.right[1][0]}
                          y1={prop.box.right[1][1]}
                          x2={prop.box.right[2][0]}
                          y2={prop.box.right[2][1]}
                          stroke="#1e293b"
                          strokeWidth="0.4"
                        />
                        {/* Illuminated Cabin Inside */}
                        <polygon
                          points={`
                            ${prop.box.right[0][0] * 0.8 + prop.box.right[3][0] * 0.2},${prop.box.right[0][1] * 0.7 + prop.box.right[3][1] * 0.3}
                            ${prop.box.right[1][0] * 0.8 + prop.box.right[2][0] * 0.2},${prop.box.right[1][1] * 0.7 + prop.box.right[2][1] * 0.3}
                            ${prop.box.right[1][0] * 0.35 + prop.box.right[2][0] * 0.65},${prop.box.right[1][1] * 0.35 + prop.box.right[2][1] * 0.65}
                            ${prop.box.right[0][0] * 0.35 + prop.box.right[3][0] * 0.65},${prop.box.right[0][1] * 0.35 + prop.box.right[3][1] * 0.65}
                          `}
                          fill="#fef08a"
                          opacity="0.8"
                          stroke="#eab308"
                          strokeWidth="0.25"
                        />
                        {/* Door Slit */}
                        <line
                          className="iso-elevator-door-line"
                          x1={prop.box.right[1][0] - 0.2}
                          y1={prop.box.right[1][1] - 0.2}
                          x2={prop.box.right[1][0] - 0.2}
                          y2={prop.box.right[1][1] - 5.5}
                          stroke="#ffffff"
                          strokeWidth="0.35"
                          strokeDasharray="1.2 0.8"
                        />
                        {/* LED Floor Indicator */}
                        <circle
                          cx={prop.box.right[1][0] - 0.2}
                          cy={prop.box.right[1][1] - 6.2}
                          r="0.35"
                          fill="#22c55e"
                        />
                      </>
                    )}
                  </g>
                )}
                {prop.ramp && (
                  <g
                    className={`iso-prop iso-prop--ramp is-${prop.ramp.direction.toLowerCase()}`}
                    data-prop-id={prop.id}
                    data-ramp-direction={prop.ramp.direction}
                  >
                    {prop.ramp.opening && (
                      <polygon
                        className="iso-ramp-opening"
                        points={pointsToPolygon(prop.ramp.opening)}
                      />
                    )}
                    <polygon
                      className="iso-prop-left"
                      points={pointsToPolygon(prop.ramp.left)}
                    />
                    <polygon
                      className="iso-prop-right"
                      points={pointsToPolygon(prop.ramp.right)}
                    />
                    <polygon
                      className="iso-ramp-deck"
                      points={pointsToPolygon(prop.ramp.deck)}
                    />
                    {/* Parapet Safety Striping */}
                    <line
                      className="iso-ramp-edge-line"
                      x1={prop.ramp.sideLines[0][0][0]}
                      y1={prop.ramp.sideLines[0][0][1]}
                      x2={prop.ramp.sideLines[0][1][0]}
                      y2={prop.ramp.sideLines[0][1][1]}
                    />
                    <line
                      className="iso-ramp-edge-line"
                      x1={prop.ramp.sideLines[1][0][0]}
                      y1={prop.ramp.sideLines[1][0][1]}
                      x2={prop.ramp.sideLines[1][1][0]}
                      y2={prop.ramp.sideLines[1][1][1]}
                    />
                    {/* Vạch tim chạy dọc theo chiều lên/xuống của dốc. */}
                    <line
                      className="iso-ramp-center-line"
                      x1={prop.ramp.centerLine[0][0]}
                      y1={prop.ramp.centerLine[0][1]}
                      x2={prop.ramp.centerLine[1][0]}
                      y2={prop.ramp.centerLine[1][1]}
                    />
                  </g>
                )}
                {prop.label && prop.labelAt && (
                  <text
                    className="iso-label iso-label--prop"
                    x={prop.labelAt[0]}
                    y={prop.labelAt[1]}
                    textAnchor="middle"
                  >
                    {prop.label}
                  </text>
                )}
              </svg>
            </div>
          );
        })}
      </div>
    </div>
  );
}

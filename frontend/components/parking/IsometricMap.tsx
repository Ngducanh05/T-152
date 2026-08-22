import React, { useMemo } from "react";

import { pointsToPolygon } from "@/lib/iso-geometry";
import { buildIsoScene } from "@/lib/iso-scene";
import type { IsoBay, IsoCarFaces, IsoProp } from "@/lib/iso-scene";
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
  onSelectSlot?: (slotId: string) => void;
  onOpenReportedSlot?: (slotId: string) => void;
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
  onSelectSlot,
  onOpenReportedSlot,
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

            const carData = bay.car as (IsoCarFaces | null);

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
                    <defs>
                      <linearGradient id={`car-glare-${bay.slotId}`} x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#ffffff" stopOpacity="0.5" />
                        <stop offset="60%" stopColor="#38bdf8" stopOpacity="0.25" />
                        <stop offset="100%" stopColor="#0f172a" stopOpacity="0.85" />
                      </linearGradient>
                    </defs>
                    <g className="iso-car" data-car-slot={bay.slotId}>
                      {/* 1. Lower body */}
                      <polygon
                        className="iso-car-left"
                        points={pointsToPolygon(carData.left)}
                      />
                      <polygon
                        className="iso-car-right"
                        points={pointsToPolygon(carData.right)}
                      />
                      <polygon
                        className="iso-car-top"
                        points={pointsToPolygon(carData.top)}
                      />

                      {/* 2. 4 Wheels (Tires & Hubcaps) */}
                      {/* Front Left Wheel */}
                      <ellipse
                        cx={carData.left[0][0] * 0.72 + carData.left[1][0] * 0.28}
                        cy={carData.left[0][1] * 0.72 + carData.left[1][1] * 0.28 + 0.15}
                        rx="0.85"
                        ry="1.0"
                        fill="#1e293b"
                        stroke="#94a3b8"
                        strokeWidth="0.2"
                      />
                      {/* Rear Left Wheel */}
                      <ellipse
                        cx={carData.left[0][0] * 0.25 + carData.left[1][0] * 0.75}
                        cy={carData.left[0][1] * 0.25 + carData.left[1][1] * 0.75 + 0.15}
                        rx="0.85"
                        ry="1.0"
                        fill="#1e293b"
                        stroke="#94a3b8"
                        strokeWidth="0.2"
                      />
                      {/* Front Right Wheel */}
                      <ellipse
                        cx={carData.right[1][0] * 0.72 + carData.right[0][0] * 0.28}
                        cy={carData.right[1][1] * 0.72 + carData.right[0][1] * 0.28 + 0.15}
                        rx="0.85"
                        ry="1.0"
                        fill="#1e293b"
                        stroke="#94a3b8"
                        strokeWidth="0.2"
                      />
                      {/* Rear Right Wheel */}
                      <ellipse
                        cx={carData.right[1][0] * 0.25 + carData.right[0][0] * 0.75}
                        cy={carData.right[1][1] * 0.25 + carData.right[0][1] * 0.75 + 0.15}
                        rx="0.85"
                        ry="1.0"
                        fill="#1e293b"
                        stroke="#94a3b8"
                        strokeWidth="0.2"
                      />

                      {/* 3. Front LED Headlights */}
                      <circle
                        cx={carData.top[2][0] * 0.85 + carData.top[3][0] * 0.15}
                        cy={carData.top[2][1] * 0.85 + carData.top[3][1] * 0.15}
                        r="0.45"
                        fill="#f8fafc"
                        stroke="#38bdf8"
                        strokeWidth="0.2"
                      />
                      <circle
                        cx={carData.top[2][0] * 0.85 + carData.top[1][0] * 0.15}
                        cy={carData.top[2][1] * 0.85 + carData.top[1][1] * 0.15}
                        r="0.45"
                        fill="#f8fafc"
                        stroke="#38bdf8"
                        strokeWidth="0.2"
                      />

                      {/* 4. Rear Red Taillights */}
                      <circle
                        cx={carData.top[0][0] * 0.85 + carData.top[3][0] * 0.15}
                        cy={carData.top[0][1] * 0.85 + carData.top[3][1] * 0.15}
                        r="0.4"
                        fill="#ef4444"
                        stroke="#991b1b"
                        strokeWidth="0.15"
                      />
                      <circle
                        cx={carData.top[0][0] * 0.85 + carData.top[1][0] * 0.15}
                        cy={carData.top[0][1] * 0.85 + carData.top[1][1] * 0.15}
                        r="0.4"
                        fill="#ef4444"
                        stroke="#991b1b"
                        strokeWidth="0.15"
                      />

                      {/* 5. Upper cabin (glass & roof) */}
                      {carData.cabinLeft && (
                        <polygon
                          className="iso-car-cabin-left"
                          points={pointsToPolygon(carData.cabinLeft)}
                        />
                      )}
                      {carData.cabinRight && (
                        <polygon
                          className="iso-car-cabin-right"
                          points={pointsToPolygon(carData.cabinRight)}
                        />
                      )}
                      {carData.cabinTop && (
                        <polygon
                          className="iso-car-cabin-top"
                          points={pointsToPolygon(carData.cabinTop)}
                        />
                      )}
                      {/* Front Windshield Glare */}
                      {carData.cabinTop && (
                        <polygon
                          className="iso-car-windshield"
                          points={`${carData.top[2][0] * 0.4 + carData.top[3][0] * 0.6},${carData.top[2][1] * 0.4 + carData.top[3][1] * 0.6} ${carData.top[2][0] * 0.4 + carData.top[1][0] * 0.6},${carData.top[2][1] * 0.4 + carData.top[1][1] * 0.6} ${carData.cabinTop[1][0]},${carData.cabinTop[1][1]} ${carData.cabinTop[3][0]},${carData.cabinTop[3][1]}`}
                          fill={`url(#car-glare-${bay.slotId})`}
                          stroke="#475569"
                          strokeWidth="0.2"
                        />
                      )}
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
                  onSelect={onSelectSlot}
                  onOpenReportedSlot={onOpenReportedSlot}
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
                    className="iso-prop iso-prop--ramp"
                    data-prop-id={prop.id}
                  >
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
                      x1={prop.ramp.left[1][0]}
                      y1={prop.ramp.left[1][1]}
                      x2={prop.ramp.left[2][0]}
                      y2={prop.ramp.left[2][1]}
                      stroke="#fbbf24"
                      strokeWidth="0.4"
                      strokeDasharray="1.5 1.0"
                    />
                    <line
                      x1={prop.ramp.right[1][0]}
                      y1={prop.ramp.right[1][1]}
                      x2={prop.ramp.right[2][0]}
                      y2={prop.ramp.right[2][1]}
                      stroke="#fbbf24"
                      strokeWidth="0.4"
                      strokeDasharray="1.5 1.0"
                    />
                    {/* Ramp Centerline */}
                    <line
                      x1={(prop.ramp.deck[0][0] + prop.ramp.deck[3][0]) / 2}
                      y1={(prop.ramp.deck[0][1] + prop.ramp.deck[3][1]) / 2}
                      x2={(prop.ramp.deck[1][0] + prop.ramp.deck[2][0]) / 2}
                      y2={(prop.ramp.deck[1][1] + prop.ramp.deck[2][1]) / 2}
                      stroke="#ffffff"
                      strokeWidth="0.3"
                      strokeDasharray="1.5 1.0"
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

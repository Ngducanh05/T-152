import {
  buildIsoBox,
  buildIsoRamp,
  buildIsoRhombus,
  buildIsoRibbonPath,
  isoDepth,
  projectIso,
  projectIsoPath,
  toIsoPercent,
} from "@/lib/iso-geometry";
import type { IsoBoxFaces, IsoRampFaces } from "@/lib/iso-geometry";
import { buildLanePath, getDisplayPoint } from "@/lib/map-geometry";
import type { MapPoint } from "@/lib/map-geometry";

function lift(point: MapPoint, height: number): MapPoint {
  return [point[0], point[1] - height];
}
import type {
  FloorId,
  MapEdge,
  MapNode,
  ParkingSlot,
  RouteResult,
  SlotStatus,
  ZoneId,
} from "@/lib/types";

export const SLAB_THICKNESS = 7;
export const BAY_HALF_W = 2.2;
export const BAY_HALF_D = 4.5;
export const CAR_HALF_W = 1.8;
export const CAR_HALF_D = 3.6;
export const CAR_HEIGHT = 5;
export const ELEVATOR_HEIGHT = 12;
export const CHECKPOINT_HEIGHT = 4;
export const RAMP_RISE = 8;
export const ROAD_W_MAIN = 7;
export const ROAD_W_RING = 6;
export const ROAD_W_SHARED = 6;
export const ROAD_W_ELEVATOR = 5.5;

export type IsoPropKind =
  | "ELEVATOR"
  | "RAMP"
  | "CHECKPOINT"
  | "ENTRANCE"
  | "EXIT";

export interface IsoSurface {
  id: string;
  points: MapPoint[];
}

export interface IsoRoad {
  id: string;
  kind: "main" | "ring" | "shared" | "elevator";
  quads: MapPoint[][];
  markings: MapPoint[];
}

export interface IsoBay {
  slotId: string;
  status: SlotStatus;
  zoneId: ZoneId;
  depth: number;
  footprint: MapPoint[];
  car: IsoBoxFaces | null;
  centerPercent: MapPoint;
}

export interface IsoProp {
  id: string;
  kind: IsoPropKind;
  depth: number;
  box: IsoBoxFaces | null;
  ramp: IsoRampFaces | null;
  labelAt: MapPoint | null;
  label: string | null;
}

export interface IsoLabel {
  id: string;
  text: string;
  at: MapPoint;
}

export interface IsoScene {
  slab: IsoBoxFaces;
  zones: IsoSurface[];
  roads: IsoRoad[];
  bays: IsoBay[];
  props: IsoProp[];
  labels: IsoLabel[];
  routePoints: MapPoint[] | null;
  currentLocationAt: MapPoint | null;
}

export interface BuildIsoSceneInput {
  floorId: FloorId;
  nodes: MapNode[];
  edges: MapEdge[];
  slots: ParkingSlot[];
  route: RouteResult | null;
  currentLocationNodeId: string | null;
}

const ZONE_RECTS: Array<{ id: string; points: MapPoint[] }> = [
  {
    id: "zone-A",
    points: [
      [22, 9],
      [48, 9],
      [48, 48],
      [22, 48],
    ],
  },
  {
    id: "zone-B",
    points: [
      [52, 9],
      [78, 9],
      [78, 48],
      [52, 48],
    ],
  },
  {
    id: "zone-C",
    points: [
      [22, 52],
      [48, 52],
      [48, 88],
      [22, 88],
    ],
  },
  {
    id: "zone-D",
    points: [
      [52, 52],
      [78, 52],
      [78, 88],
      [52, 88],
    ],
  },
];

export interface IsoCarFaces extends IsoBoxFaces {
  cabinTop?: MapPoint[];
  cabinLeft?: MapPoint[];
  cabinRight?: MapPoint[];
}

export function buildIsoCar(center: MapPoint): IsoCarFaces {
  // 1. Thân xe (chassis) thấp dài
  const body = buildIsoBox(center, CAR_HALF_W, CAR_HALF_D, 2.2);

  // 2. Cabin / mui kính ở nửa sau xe (từ cao độ 2.2 đến 4.6)
  const cabinCenter: MapPoint = [center[0], center[1] - 0.5];
  const [p0, p1, p2, p3] = buildIsoRhombus(cabinCenter, CAR_HALF_W * 0.82, CAR_HALF_D * 0.55);
  const base1 = lift(p1, 2.2);
  const base2 = lift(p2, 2.2);
  const base3 = lift(p3, 2.2);
  const top0 = lift(p0, 4.6);
  const top1 = lift(p1, 4.6);
  const top2 = lift(p2, 4.6);
  const top3 = lift(p3, 4.6);

  return {
    top: body.top,
    left: body.left,
    right: body.right,
    cabinTop: [top0, top1, top2, top3],
    cabinLeft: [base2, base3, top3, top2],
    cabinRight: [base1, base2, top2, top1],
  };
}

/**
 * Biến dữ liệu sơ đồ bãi xe thành mô tả cảnh isometric đã sắp xếp thứ tự vẽ.
 */
export function buildIsoScene(input: BuildIsoSceneInput): IsoScene {
  const { floorId, nodes, slots, route, currentLocationNodeId } = input;

  const nodeById = new Map<string, MapNode>(
    nodes.map((node) => [node.id, node]),
  );

  // 1. Khối sàn (extrude xuống 7 đơn vị)
  const slab = buildIsoBox([50, 50], 50, 50, -SLAB_THICKNESS);

  // 2. Mặt khu A-D
  const zones: IsoSurface[] = ZONE_RECTS.map((z) => ({
    id: z.id,
    points: projectIsoPath(z.points),
  }));

  // 3 & 4. Đường xe chạy & vạch kẻ đường
  const mainRoadPoints: MapPoint[] =
    floorId === "F1"
      ? [
          [0, 50],
          [100, 50],
        ]
      : [
          [15, 50],
          [85, 50],
        ];

  const ringNorthPoints: MapPoint[] = [
    [20, 50],
    [20, 7],
    [80, 7],
    [80, 50],
  ];

  const sharedNorthPoints: MapPoint[] = [
    [50, 7],
    [50, 50],
  ];

  const ringSouthPoints: MapPoint[] = [
    [20, 50],
    [20, 90],
    [80, 90],
    [80, 50],
  ];

  const elevatorRoadPoints: MapPoint[] = [
    [50, 50],
    [50, 90],
  ];

  const roads: IsoRoad[] = [
    {
      id: "main-road",
      kind: "main",
      quads: buildIsoRibbonPath(mainRoadPoints, ROAD_W_MAIN),
      markings: projectIsoPath(mainRoadPoints),
    },
    {
      id: "zone-ring-north",
      kind: "ring",
      quads: buildIsoRibbonPath(ringNorthPoints, ROAD_W_RING),
      markings: projectIsoPath(ringNorthPoints),
    },
    {
      id: "shared-road-north",
      kind: "shared",
      quads: buildIsoRibbonPath(sharedNorthPoints, ROAD_W_SHARED),
      markings: projectIsoPath(sharedNorthPoints),
    },
    {
      id: "zone-ring-south",
      kind: "ring",
      quads: buildIsoRibbonPath(ringSouthPoints, ROAD_W_RING),
      markings: projectIsoPath(ringSouthPoints),
    },
    {
      id: "shared-road-elevator",
      kind: "elevator",
      quads: buildIsoRibbonPath(elevatorRoadPoints, ROAD_W_ELEVATOR),
      markings: projectIsoPath(elevatorRoadPoints),
    },
  ];

  // 5 & 6. Khoang đỗ và xe đang đỗ
  const bays: IsoBay[] = slots
    .map((slot) => {
      const slotNode = nodeById.get(slot.id);
      if (!slotNode) return null;
      const center = getDisplayPoint(slotNode);
      const depth = isoDepth(center);
      const footprint = buildIsoRhombus(center, BAY_HALF_W, BAY_HALF_D);
      const car = slot.status === "OCCUPIED" ? buildIsoCar(center) : null;
      const centerPercent = toIsoPercent(projectIso(center));

      return {
        slotId: slot.id,
        status: slot.status,
        zoneId: slot.zone_id,
        depth,
        footprint,
        car,
        centerPercent,
      };
    })
    .filter((bay): bay is IsoBay => bay !== null);

  // Sắp xếp bays tăng dần theo depth (xa tới gần)
  bays.sort((a, b) => a.depth - b.depth);

  // 7. Vật thể hạ tầng (Props)
  const props: IsoProp[] = [];

  for (const node of nodes) {
    if (node.type === "SLOT" || node.type === "AISLE") continue;

    const center = getDisplayPoint(node);
    const depth = isoDepth(center);

    if (node.type === "ENTRANCE") {
      props.push({
        id: node.id,
        kind: "ENTRANCE",
        depth,
        box: null,
        ramp: null,
        labelAt: projectIso([4.5, node.y - 2.3]),
        label: "LỐI VÀO",
      });
    } else if (node.type === "EXIT") {
      props.push({
        id: node.id,
        kind: "EXIT",
        depth,
        box: null,
        ramp: null,
        labelAt: projectIso([95.5, node.y - 2.3]),
        label: "LỐI RA",
      });
    } else if (node.type === "ELEVATOR") {
      props.push({
        id: node.id,
        kind: "ELEVATOR",
        depth,
        box: buildIsoBox(center, 1.8, 1.8, ELEVATOR_HEIGHT),
        ramp: null,
        labelAt: projectIso([50, 101]),
        label: "↕ THANG MÁY",
      });
    } else if (node.type === "RAMP") {
      if (floorId === "F1") {
        // F1: Dốc đi xuống tầng F2 (vị trí cũ [85, 75], nhãn tách biệt dưới chân dốc)
        props.push({
          id: node.id,
          kind: "RAMP",
          depth,
          box: null,
          ramp: buildIsoRamp(center, 3.6, 4.5, -6),
          labelAt: projectIso([center[0], center[1] + 11.5]),
          label: "↓ Xuống F2",
        });
      } else if (floorId === "F3") {
        // F3: Dốc đi lên tầng F2 (di chuyển sang vị trí mới [14, 32] cặp với Xuống F3 của F2)
        const f3RampCenter: MapPoint = [14, 32];
        props.push({
          id: node.id,
          kind: "RAMP",
          depth: isoDepth(f3RampCenter),
          box: null,
          ramp: buildIsoRamp(f3RampCenter, 3.6, 4.5, 6),
          labelAt: projectIso([f3RampCenter[0], f3RampCenter[1] - 11.5]),
          label: "↑ Lên F2",
        });
      } else {
        if (node.id !== "F2-RAMP") {
          continue;
        }
        // F2: 2 dốc tách biệt
        // 1. Dốc lên F1: Giữ nguyên vị trí cũ [85, 75]
        props.push({
          id: `${node.id}-up`,
          kind: "RAMP",
          depth: isoDepth(center),
          box: null,
          ramp: buildIsoRamp(center, 3.6, 4.5, 6),
          labelAt: projectIso([center[0], center[1] - 9.5]),
          label: "↑ Lên F1",
        });
        // 2. Dốc xuống F3: Vị trí mới [14, 32] (khu vực khoanh đỏ)
        const f2DownCenter: MapPoint = [14, 32];
        props.push({
          id: `${node.id}-down`,
          kind: "RAMP",
          depth: isoDepth(f2DownCenter),
          box: null,
          ramp: buildIsoRamp(f2DownCenter, 3.6, 4.5, -6),
          labelAt: projectIso([f2DownCenter[0], f2DownCenter[1] + 12.5]),
          label: "↓ Xuống F3",
        });
      }
    } else if (node.type === "CHECKPOINT") {
      props.push({
        id: node.id,
        kind: "CHECKPOINT",
        depth,
        box: buildIsoBox(center, 1.2, 1.2, CHECKPOINT_HEIGHT),
        ramp: null,
        labelAt: projectIso([center[0], center[1] - 2.3]),
        label: node.id.replace(/^F[1-3]-/, ""),
      });
    }
  }

  // Sắp xếp props tăng dần theo depth
  props.sort((a, b) => a.depth - b.depth);

  // 8. Nhãn khu vực
  const zoneIds: ZoneId[] = ["A", "B", "C", "D"];
  const labels: IsoLabel[] = zoneIds.flatMap((zoneId) => {
    const zoneSlots = slots.filter((slot) => slot.zone_id === zoneId);
    const zoneNodes = zoneSlots
      .map((slot) => nodeById.get(slot.id))
      .filter((node): node is MapNode => Boolean(node));
    if (zoneNodes.length === 0) return [];
    const avgX =
      zoneNodes.reduce((sum, node) => sum + node.x, 0) / zoneNodes.length;
    const sourceY = zoneId === "A" || zoneId === "B" ? 10 : 55;
    return [
      {
        id: `label-zone-${zoneId}`,
        text: `KHU ${zoneId}`,
        at: projectIso([avgX, sourceY]),
      },
    ];
  });

  // 9. Tuyến đường (Route)
  let routePoints: MapPoint[] | null = null;
  if (route && route.path.length >= 2) {
    const floorRouteNodes: MapNode[] = [];
    let allFound = true;
    for (const nodeId of route.path) {
      const node = nodeById.get(nodeId);
      if (!node) {
        allFound = false;
        break;
      }
      floorRouteNodes.push(node);
    }

    if (allFound && floorRouteNodes.length === route.path.length) {
      routePoints = projectIsoPath(buildLanePath(floorRouteNodes));
    }
  }

  // 10. Vị trí hiện tại
  let currentLocationAt: MapPoint | null = null;
  if (currentLocationNodeId) {
    const currentNode = nodeById.get(currentLocationNodeId);
    if (currentNode && currentNode.type !== "SLOT") {
      currentLocationAt = projectIso(getDisplayPoint(currentNode));
    }
  }

  return {
    slab,
    zones,
    roads,
    bays,
    props,
    labels,
    routePoints,
    currentLocationAt,
  };
}

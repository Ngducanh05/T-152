import { formatParkingLocation } from "./parking-display";
import type { ParkingMap, RouteResult } from "./types";

export type RouteInstructionKind =
  | "START"
  | "STRAIGHT"
  | "LEFT"
  | "RIGHT"
  | "U_TURN"
  | "CONTINUE"
  | "ARRIVE";

export interface RouteInstruction {
  nodeId: string;
  kind: RouteInstructionKind;
  icon: string;
  label: string;
  description: string;
}

type Point = readonly [number, number];

const PRESENTATION = {
  START: { icon: "●", label: "Bắt đầu" },
  STRAIGHT: { icon: "↑", label: "Đi thẳng" },
  LEFT: { icon: "↰", label: "Rẽ trái" },
  RIGHT: { icon: "↱", label: "Rẽ phải" },
  U_TURN: { icon: "↶", label: "Quay lại" },
  CONTINUE: { icon: "→", label: "Tiếp tục" },
  ARRIVE: { icon: "P", label: "Đến nơi" },
} as const;

function naturalDirection(
  kind: RouteInstructionKind,
  atIntersection: boolean,
): string {
  if (kind === "LEFT" || kind === "RIGHT") {
    const place = atIntersection ? "Ở ngã tư phía trước" : "Tới lối rẽ phía trước";
    return `${place}, ${kind === "LEFT" ? "rẽ trái" : "rẽ phải"}.`;
  }
  if (kind === "STRAIGHT") {
    return atIntersection
      ? "Qua ngã tư phía trước, tiếp tục đi thẳng."
      : "Tiếp tục đi thẳng theo lối phía trước.";
  }
  if (kind === "U_TURN") {
    return "Khi tới chỗ quay đầu phía trước, quay lại.";
  }
  return "Tiếp tục đi theo lối phía trước.";
}

function routePoints(route: RouteResult, map: ParkingMap | null): Array<Point | null> {
  if (route.polyline.length === route.path.length) {
    return route.polyline;
  }
  const nodeById = new Map(map?.nodes.map((node) => [node.id, node]) ?? []);
  return route.path.map((nodeId) => {
    const node = nodeById.get(nodeId);
    return node ? [node.x, node.y] : null;
  });
}

function turnKind(
  previous: Point | null,
  current: Point | null,
  next: Point | null,
): RouteInstructionKind {
  if (!previous || !current || !next) return "CONTINUE";
  const incomingX = current[0] - previous[0];
  const incomingY = current[1] - previous[1];
  const outgoingX = next[0] - current[0];
  const outgoingY = next[1] - current[1];
  const incomingLength = Math.hypot(incomingX, incomingY);
  const outgoingLength = Math.hypot(outgoingX, outgoingY);
  if (incomingLength === 0 || outgoingLength === 0) return "CONTINUE";

  const cross = incomingX * outgoingY - incomingY * outgoingX;
  const dot = incomingX * outgoingX + incomingY * outgoingY;
  const angle = Math.atan2(Math.abs(cross), dot) * (180 / Math.PI);
  if (angle < 25) return "STRAIGHT";
  if (angle > 155) return "U_TURN";
  // Parking-map coordinates use a screen axis where y grows downward.
  return cross > 0 ? "RIGHT" : "LEFT";
}

export function buildRouteInstructions(
  route: RouteResult,
  map: ParkingMap | null,
): RouteInstruction[] {
  if (route.path.length === 0) return [];
  if (route.path.length === 1) {
    const destination = formatParkingLocation(route.path[0]);
    return [{
      nodeId: route.path[0],
      kind: "ARRIVE",
      ...PRESENTATION.ARRIVE,
      description: `Bạn đã ở ${destination}.`,
    }];
  }

  const points = routePoints(route, map);
  const nodeById = new Map(map?.nodes.map((node) => [node.id, node]) ?? []);
  return route.path.map((nodeId, index) => {
    if (index === 0) {
      return {
        nodeId,
        kind: "START" as const,
        ...PRESENTATION.START,
        description: "Đi theo lối ngay phía trước.",
      };
    }
    if (index === route.path.length - 1) {
      const destination = formatParkingLocation(nodeId);
      return {
        nodeId,
        kind: "ARRIVE" as const,
        ...PRESENTATION.ARRIVE,
        description: `Bạn sẽ đến ${destination}.`,
      };
    }

    const kind = turnKind(points[index - 1], points[index], points[index + 1]);
    const presentation = PRESENTATION[kind];
    return {
      nodeId,
      kind,
      ...presentation,
      description: naturalDirection(
        kind,
        nodeById.get(nodeId)?.type === "CHECKPOINT",
      ),
    };
  });
}

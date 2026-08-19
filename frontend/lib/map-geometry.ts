import type { MapNode } from "@/lib/types";

export type MapPoint = [number, number];

const SLOT_PATTERN = /^(?:F[1-3])-([A-D])(\d{2})$/;
const AISLE_PATTERN = /^(?:F[1-3])-([A-D])-(W|E)$/;

const ZONE_ROAD_BOUNDS = {
  A: { left: 20, right: 50, nearMain: 50, outer: 7, north: true },
  B: { left: 50, right: 80, nearMain: 50, outer: 7, north: true },
  C: { left: 20, right: 50, nearMain: 50, outer: 90, north: false },
  D: { left: 50, right: 80, nearMain: 50, outer: 90, north: false },
} as const;

/**
 * The API coordinates describe the routing graph. Slot rows need a little more
 * visual separation so a parking bay can be drawn at a useful, tappable size.
 */
export function getDisplayPoint(node: MapNode): MapPoint {
  if (node.type === "ELEVATOR") return [50, 96];

  if (node.type === "AISLE") {
    const aisleMatch = AISLE_PATTERN.exec(node.id);
    if (aisleMatch) {
      const zone = aisleMatch[1] as keyof typeof ZONE_ROAD_BOUNDS;
      const side = aisleMatch[2];
      const bounds = ZONE_ROAD_BOUNDS[zone];
      return [side === "W" ? bounds.left : bounds.right, bounds.nearMain];
    }
  }

  if (node.type !== "SLOT") return [node.x, node.y];

  const match = SLOT_PATTERN.exec(node.id);
  if (!match) return [node.x, node.y];

  const zone = match[1];
  const slotNumber = Number(match[2]);
  const isNorth = zone === "A" || zone === "B";
  const isFirstBank = slotNumber <= 5;
  const positionInBank = (slotNumber - 1) % 5;
  const zoneLeft = zone === "A" || zone === "C" ? 20 : 50;
  const displayX = zoneLeft + 5 + positionInBank * 5;

  if (isNorth) return [displayX, isFirstBank ? 18 : 39];
  return [displayX, isFirstBank ? 61 : 82];
}

function samePoint(a: MapPoint, b: MapPoint) {
  return a[0] === b[0] && a[1] === b[1];
}

function compact(points: MapPoint[]) {
  return points.filter(
    (point, index) => index === 0 || !samePoint(point, points[index - 1]),
  );
}

/** Build an orthogonal lane between graph nodes instead of cutting diagonally. */
export function buildLaneSegment(from: MapNode, to: MapNode): MapPoint[] {
  const start = getDisplayPoint(from);
  const end = getDisplayPoint(to);
  const aisle = from.type === "AISLE" ? from : to.type === "AISLE" ? to : null;
  const elevator =
    from.type === "ELEVATOR" ? from : to.type === "ELEVATOR" ? to : null;

  // Both graph links merge into the shared centre road. The road stops at the
  // lobby edge so the elevator marker can sit separately below it.
  if (aisle && elevator) {
    const aislePoint = getDisplayPoint(aisle);
    const elevatorLobbyPoint: MapPoint = [50, 91];
    const aisleToElevator = compact([
      aislePoint,
      [elevatorLobbyPoint[0], aislePoint[1]],
      elevatorLobbyPoint,
    ]);
    return from.type === "AISLE"
      ? aisleToElevator
      : aisleToElevator.reverse();
  }

  if (start[0] === end[0] || start[1] === end[1]) return [start, end];

  const slot = from.type === "SLOT" ? from : to.type === "SLOT" ? to : null;
  if (aisle && slot) {
    const aislePoint = getDisplayPoint(aisle);
    const slotPoint = getDisplayPoint(slot);
    const match = SLOT_PATTERN.exec(slot.id);
    if (!match) return compact([aislePoint, [slotPoint[0], aislePoint[1]], slotPoint]);

    const zone = match[1] as keyof typeof ZONE_ROAD_BOUNDS;
    const slotNumber = Number(match[2]);
    const bounds = ZONE_ROAD_BOUNDS[zone];
    const usesOuterRoad = bounds.north ? slotNumber <= 5 : slotNumber > 5;
    const accessY = usesOuterRoad ? bounds.outer : bounds.nearMain;
    const aisleToSlot = compact([
      aislePoint,
      [aislePoint[0], accessY],
      [slotPoint[0], accessY],
      slotPoint,
    ]);
    return from.type === "AISLE" ? aisleToSlot : aisleToSlot.reverse();
  }

  const checkpoint =
    from.type === "CHECKPOINT" ? from : to.type === "CHECKPOINT" ? to : null;
  if (aisle && checkpoint) {
    const aislePoint = getDisplayPoint(aisle);
    const checkpointPoint = getDisplayPoint(checkpoint);
    const checkpointToAisle = compact([
      checkpointPoint,
      [checkpointPoint[0], aislePoint[1]],
      aislePoint,
    ]);
    return from.type === "CHECKPOINT"
      ? checkpointToAisle
      : checkpointToAisle.reverse();
  }

  return compact([start, [start[0], end[1]], end]);
}

export function buildLanePath(nodes: MapNode[]): MapPoint[] {
  if (nodes.length < 2) return nodes.map(getDisplayPoint);

  const points: MapPoint[] = [];
  for (let index = 1; index < nodes.length; index += 1) {
    const segment = buildLaneSegment(nodes[index - 1], nodes[index]);
    points.push(...(index === 1 ? segment : segment.slice(1)));
  }
  return compact(points);
}

export function pointsToPath(points: MapPoint[]) {
  return points
    .map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x} ${y}`)
    .join(" ");
}

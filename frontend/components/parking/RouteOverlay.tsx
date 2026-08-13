import { buildLanePath } from "@/lib/map-geometry";
import type { MapNode, RouteResult } from "@/lib/types";

export interface RouteOverlayProps {
  route: RouteResult | null;
  nodeById?: Map<string, MapNode>;
}

export function RouteOverlay({ route, nodeById }: RouteOverlayProps) {
  if (!route) return null;

  const routeNodes = route.path
    .map((nodeId) => nodeById?.get(nodeId))
    .filter((node): node is MapNode => node !== undefined);
  const visualPoints =
    routeNodes.length === route.path.length
      ? buildLanePath(routeNodes)
      : route.polyline;
  const points = visualPoints.map(([x, y]) => `${x},${y}`).join(" ");

  return (
    <g className="map-route" aria-label={`Active route, ${route.distance_m} metres`}>
      <defs>
        <marker
          id="route-arrow"
          viewBox="0 0 10 10"
          refX="8"
          refY="5"
          markerWidth="5"
          markerHeight="5"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" />
        </marker>
      </defs>
      <polyline
        className="map-route-glow"
        points={points}
        fill="none"
        aria-hidden="true"
      />
      <polyline
        className="map-route-line"
        points={points}
        fill="none"
        markerEnd="url(#route-arrow)"
        data-testid="route-polyline"
      />
    </g>
  );
}

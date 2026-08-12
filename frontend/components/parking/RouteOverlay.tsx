import type { RouteResult } from "@/lib/types";

export interface RouteOverlayProps {
  route: RouteResult | null;
}

export function RouteOverlay({ route }: RouteOverlayProps) {
  if (!route) return null;

  const points = route.polyline.map(([x, y]) => `${x},${y}`).join(" ");

  return (
    <g className="map-route" aria-label={`Active route, ${route.distance_m} metres`}>
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
        data-testid="route-polyline"
      />
    </g>
  );
}

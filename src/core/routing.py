"""Deterministic Dijkstra routing over the persisted parking graph."""

from heapq import heappop, heappush

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import MapEdge, MapNode
from src.models.schemas import ErrorCode, RouteResult


class RoutingError(Exception):
    """Core routing error with a stable API-independent error code."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class RoutingService:
    """Load enabled database edges and calculate deterministic shortest paths."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_route(
        self,
        start_node_id: str,
        destination_node_id: str,
    ) -> RouteResult:
        nodes = list(
            await self.session.scalars(select(MapNode).order_by(MapNode.id))
        )
        node_by_id = {node.id: node for node in nodes}
        self._validate_endpoints(node_by_id, start_node_id, destination_node_id)

        if start_node_id == destination_node_id:
            node = node_by_id[start_node_id]
            return RouteResult(
                path=[start_node_id],
                distance_m=0,
                polyline=[(node.x, node.y)],
            )

        edges = list(
            await self.session.scalars(
                select(MapEdge)
                .where(MapEdge.enabled.is_(True))
                .order_by(MapEdge.from_node, MapEdge.to_node)
            )
        )
        adjacency = self._build_adjacency(node_by_id, edges)
        distance, path = self._dijkstra(
            adjacency,
            start_node_id,
            destination_node_id,
        )
        if path is None:
            raise RoutingError(
                ErrorCode.ROUTE_NOT_FOUND,
                f"No route exists from {start_node_id} to {destination_node_id}",
                details={
                    "start_node_id": start_node_id,
                    "destination_node_id": destination_node_id,
                },
            )

        return RouteResult(
            path=list(path),
            distance_m=distance,
            polyline=[(node_by_id[node_id].x, node_by_id[node_id].y) for node_id in path],
        )

    @staticmethod
    def _validate_endpoints(
        node_by_id: dict[str, MapNode],
        start_node_id: str,
        destination_node_id: str,
    ) -> None:
        missing_node_ids = [
            node_id
            for node_id in (start_node_id, destination_node_id)
            if node_id not in node_by_id
        ]
        if missing_node_ids:
            raise RoutingError(
                ErrorCode.ROUTE_NODE_NOT_FOUND,
                f"Route node {missing_node_ids[0]} was not found",
                details={"node_ids": missing_node_ids},
            )

    @staticmethod
    def _build_adjacency(
        node_by_id: dict[str, MapNode],
        edges: list[MapEdge],
    ) -> dict[str, list[tuple[str, float]]]:
        adjacency: dict[str, list[tuple[str, float]]] = {
            node_id: [] for node_id in node_by_id
        }
        for edge in edges:
            if edge.from_node not in node_by_id or edge.to_node not in node_by_id:
                continue
            adjacency[edge.from_node].append((edge.to_node, edge.distance_m))
            if edge.bidirectional:
                adjacency[edge.to_node].append((edge.from_node, edge.distance_m))
        for neighbors in adjacency.values():
            neighbors.sort(key=lambda neighbor: (neighbor[0], neighbor[1]))
        return adjacency

    @staticmethod
    def _dijkstra(
        adjacency: dict[str, list[tuple[str, float]]],
        start_node_id: str,
        destination_node_id: str,
    ) -> tuple[float, tuple[str, ...] | None]:
        start_path = (start_node_id,)
        best: dict[str, tuple[float, tuple[str, ...]]] = {
            start_node_id: (0.0, start_path)
        }
        queue: list[tuple[float, tuple[str, ...], str]] = [
            (0.0, start_path, start_node_id)
        ]

        while queue:
            distance, path, current = heappop(queue)
            if best.get(current) != (distance, path):
                continue
            if current == destination_node_id:
                return distance, path

            for neighbor, edge_distance in adjacency[current]:
                candidate = (distance + edge_distance, (*path, neighbor))
                if neighbor not in best or candidate < best[neighbor]:
                    best[neighbor] = candidate
                    heappush(queue, (candidate[0], candidate[1], neighbor))

        return 0.0, None


async def get_route(
    session: AsyncSession,
    start_node_id: str,
    destination_node_id: str,
) -> RouteResult:
    return await RoutingService(session).get_route(start_node_id, destination_node_id)


__all__ = ["RoutingError", "RoutingService", "get_route"]

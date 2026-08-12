"""Deterministic Dijkstra routing over the persisted parking graph."""

from dataclasses import dataclass
from heapq import heappop, heappush

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db_models import MapEdge, MapNode
from src.models.schemas import ErrorCode, RouteResult


@dataclass(frozen=True, slots=True)
class RoutingNode:
    """Database-independent node data retained in one graph snapshot."""

    id: str
    floor_id: str
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class RoutingGraph:
    """Enabled graph snapshot with forward and reverse adjacency."""

    nodes: dict[str, RoutingNode]
    adjacency: dict[str, tuple[tuple[str, float], ...]]
    reverse_adjacency: dict[str, tuple[tuple[str, float], ...]]


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
        graph = await self.load_graph()
        return self.route_on_graph(graph, start_node_id, destination_node_id)

    async def load_graph(self) -> RoutingGraph:
        """Load one current snapshot of nodes and enabled edges from the database."""
        nodes = list(await self.session.scalars(select(MapNode).order_by(MapNode.id)))
        edges = list(
            await self.session.scalars(
                select(MapEdge).where(MapEdge.enabled.is_(True)).order_by(MapEdge.from_node, MapEdge.to_node)
            )
        )
        node_by_id = {
            node.id: RoutingNode(
                id=node.id,
                floor_id=node.floor_id,
                x=node.x,
                y=node.y,
            )
            for node in nodes
        }
        adjacency, reverse_adjacency = self._build_adjacencies(node_by_id, edges)
        return RoutingGraph(
            nodes=node_by_id,
            adjacency=adjacency,
            reverse_adjacency=reverse_adjacency,
        )

    def route_on_graph(
        self,
        graph: RoutingGraph,
        start_node_id: str,
        destination_node_id: str,
    ) -> RouteResult:
        """Calculate a route without reloading an already current graph snapshot."""
        self._validate_endpoints(graph.nodes, start_node_id, destination_node_id)

        if start_node_id == destination_node_id:
            node = graph.nodes[start_node_id]
            return RouteResult(
                path=[start_node_id],
                distance_m=0,
                polyline=[(node.x, node.y)],
            )

        distance, path = self._dijkstra(
            graph.adjacency,
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
            polyline=[(graph.nodes[node_id].x, graph.nodes[node_id].y) for node_id in path],
        )

    def shortest_distances(
        self,
        graph: RoutingGraph,
        start_node_id: str,
        *,
        reverse: bool = False,
    ) -> dict[str, float]:
        """Return finite SSSP distances over one graph snapshot."""
        self._validate_node(graph.nodes, start_node_id)
        adjacency = graph.reverse_adjacency if reverse else graph.adjacency
        distances = {start_node_id: 0.0}
        queue: list[tuple[float, str]] = [(0.0, start_node_id)]

        while queue:
            distance, current = heappop(queue)
            if distance != distances.get(current):
                continue
            for neighbor, edge_distance in adjacency[current]:
                candidate_distance = distance + edge_distance
                if candidate_distance < distances.get(neighbor, float("inf")):
                    distances[neighbor] = candidate_distance
                    heappush(queue, (candidate_distance, neighbor))

        return distances

    @staticmethod
    def _validate_endpoints(
        node_by_id: dict[str, RoutingNode],
        start_node_id: str,
        destination_node_id: str,
    ) -> None:
        missing_node_ids = [node_id for node_id in (start_node_id, destination_node_id) if node_id not in node_by_id]
        if missing_node_ids:
            raise RoutingError(
                ErrorCode.ROUTE_NODE_NOT_FOUND,
                f"Route node {missing_node_ids[0]} was not found",
                details={"node_ids": missing_node_ids},
            )

    @staticmethod
    def _validate_node(
        node_by_id: dict[str, RoutingNode],
        node_id: str,
    ) -> None:
        if node_id not in node_by_id:
            raise RoutingError(
                ErrorCode.ROUTE_NODE_NOT_FOUND,
                f"Route node {node_id} was not found",
                details={"node_ids": [node_id]},
            )

    @staticmethod
    def _build_adjacencies(
        node_by_id: dict[str, RoutingNode],
        edges: list[MapEdge],
    ) -> tuple[
        dict[str, tuple[tuple[str, float], ...]],
        dict[str, tuple[tuple[str, float], ...]],
    ]:
        adjacency_lists: dict[str, list[tuple[str, float]]] = {node_id: [] for node_id in node_by_id}
        reverse_lists: dict[str, list[tuple[str, float]]] = {node_id: [] for node_id in node_by_id}
        for edge in edges:
            if edge.from_node not in node_by_id or edge.to_node not in node_by_id:
                continue
            adjacency_lists[edge.from_node].append((edge.to_node, edge.distance_m))
            reverse_lists[edge.to_node].append((edge.from_node, edge.distance_m))
            if edge.bidirectional:
                adjacency_lists[edge.to_node].append((edge.from_node, edge.distance_m))
                reverse_lists[edge.from_node].append((edge.to_node, edge.distance_m))

        def freeze(
            lists: dict[str, list[tuple[str, float]]],
        ) -> dict[str, tuple[tuple[str, float], ...]]:
            return {
                node_id: tuple(sorted(neighbors, key=lambda item: (item[0], item[1])))
                for node_id, neighbors in lists.items()
            }

        return freeze(adjacency_lists), freeze(reverse_lists)

    @staticmethod
    def _dijkstra(
        adjacency: dict[str, tuple[tuple[str, float], ...]],
        start_node_id: str,
        destination_node_id: str,
    ) -> tuple[float, tuple[str, ...] | None]:
        distances = {start_node_id: 0.0}
        predecessors: dict[str, str] = {}
        queue: list[tuple[float, str]] = [(0.0, start_node_id)]

        while queue:
            distance, current = heappop(queue)
            if distance != distances.get(current):
                continue
            if current == destination_node_id:
                return distance, RoutingService._reconstruct_path(
                    predecessors,
                    start_node_id,
                    destination_node_id,
                )

            for neighbor, edge_distance in adjacency[current]:
                candidate_distance = distance + edge_distance
                known_distance = distances.get(neighbor)
                known_predecessor = predecessors.get(neighbor)
                is_shorter = known_distance is None or candidate_distance < known_distance
                is_alphabetical_tie = (
                    candidate_distance == known_distance
                    and known_predecessor is not None
                    and current < known_predecessor
                )
                if is_shorter or is_alphabetical_tie:
                    distances[neighbor] = candidate_distance
                    predecessors[neighbor] = current
                    heappush(queue, (candidate_distance, neighbor))

        return 0.0, None

    @staticmethod
    def _reconstruct_path(
        predecessors: dict[str, str],
        start_node_id: str,
        destination_node_id: str,
    ) -> tuple[str, ...]:
        reversed_path = [destination_node_id]
        current = destination_node_id
        while current != start_node_id:
            current = predecessors[current]
            reversed_path.append(current)
        return tuple(reversed(reversed_path))


async def get_route(
    session: AsyncSession,
    start_node_id: str,
    destination_node_id: str,
) -> RouteResult:
    return await RoutingService(session).get_route(start_node_id, destination_node_id)


__all__ = [
    "RoutingError",
    "RoutingGraph",
    "RoutingNode",
    "RoutingService",
    "get_route",
]

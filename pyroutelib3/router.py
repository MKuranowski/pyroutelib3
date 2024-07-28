# © Copyright 2024 Mikołaj Kuranowski
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import dataclass, field
from heapq import heappop, heappush
from math import inf
from typing import Dict, List, Mapping, Optional

from .distance import haversine_earth_distance
from .protocols import DistanceFunction, ExternalNodeLike, GraphLike, NodeLike


@dataclass(frozen=True, order=True)
class _AStarQueueItem:
    node_id: int = field(compare=False)
    cost: float = field(compare=False)
    score: float = field(compare=True)
    external_id_before: Optional[int] = field(default=None, compare=False)


@dataclass(frozen=True)
class _NodeAndBefore:
    node_id: int
    external_id_before: Optional[int] = None


class StepLimitExceeded(ValueError):
    """Exception used when a route search has exceeded its limit of steps.
    Either the nodes are really far apart, or no route exists.

    Concluding that no route exists requires traversing the whole graph,
    which on real OpenStreetMap data may require going through the whole planet,
    hence this exception.
    """

    pass


DEFAULT_STEP_LIMIT = 1_000_000
"""Default number of allowed node expansions in :py:func:`find_route` and
:py:func:`find_route_without_turn_around`.
"""


def find_route(
    g: GraphLike[NodeLike],
    start: int,
    end: int,
    distance: DistanceFunction = haversine_earth_distance,
    step_limit: Optional[int] = DEFAULT_STEP_LIMIT,
) -> List[int]:
    """find_route uses the `A* algorithm <https://en.wikipedia.org/wiki/A*_search_algorithm>`_
    to find the shortest route between two nodes in the provided graph.

    Returns an empty list if there is no route between the two nodes.

    For graphs with turn restrictions, use :py:func:`find_route_without_turn_around`,
    as this implementation will generate instructions with immediate turn-arounds
    (A-B-A) to circumvent any restrictions.

    ``step_limit`` (if not None) limits how many nodes may be expanded during the search
    before raising :py:exc:`StepLimitExceeded`. Concluding that no route exists requires
    expanding all nodes accessible from the start, which is usually very time-consuming,
    especially on large datasets (like the whole planet). Defaults to
    :py:const:`DEFAULT_STEP_LIMIT`. Only set to ``None`` on small, contained graphs.
    """
    queue: List[_AStarQueueItem] = []
    came_from: Dict[int, int] = {}
    known_costs: Dict[int, float] = {}
    end_position = g.get_node(end).position
    steps = 0

    # Push the start element onto the queue
    queue.append(
        _AStarQueueItem(
            node_id=start,
            cost=0.0,
            score=distance(end_position, g.get_node(start).position),
        )
    )
    known_costs[start] = 0.0

    while queue:
        item = heappop(queue)

        if item.node_id == end:
            return _reconstruct_path(came_from, end)

        # Contrary to the Wikipedia definition, in this implementation there can be
        # many queue elements representing the same node. For example, a way to node X
        # could first be encountered with a cost of 10, but further down the line another
        # way to node X with cost of 5 could be found.
        # Ignore re-expanding nodes if a cheaper way was found earlier
        if item.cost > known_costs.get(item.node_id, inf):
            continue

        steps += 1
        if step_limit is not None and steps > step_limit:
            raise StepLimitExceeded()

        for neighbor_id, cost in g.get_edges(item.node_id):
            neighbor_cost = item.cost + cost
            if neighbor_cost < known_costs.get(neighbor_id, inf):
                neighbor_position = g.get_node(neighbor_id).position
                came_from[neighbor_id] = item.node_id
                known_costs[neighbor_id] = neighbor_cost
                neighbor_score = neighbor_cost + distance(end_position, neighbor_position)
                heappush(queue, _AStarQueueItem(neighbor_id, neighbor_cost, neighbor_score))

    return []


def find_route_without_turn_around(
    g: GraphLike[ExternalNodeLike],
    start: int,
    end: int,
    distance: DistanceFunction = haversine_earth_distance,
    step_limit: Optional[int] = DEFAULT_STEP_LIMIT,
) -> List[int]:
    """find_route_without_turn_around uses the `A* algorithm <https://en.wikipedia.org/wiki/A*_search_algorithm>`_
    to find the shortest route between two points in the provided graph.

    Returns an empty list if there is no route between the two points.

    For graphs without turn restrictions, use :py:func:`find_route`,
    as it runs faster. ``find_route_without_turn_around`` has an extra search dimension -
    it needs to not only consider the node, but also what was the previous node to prevent
    A-B-A immediate turn-around instructions.

    ``step_limit`` (if not None) limits how many nodes may be expanded during the search
    before raising :py:exc:`StepLimitExceeded`. Concluding that no route exists requires
    expanding all nodes accessible from the start, which is usually very time-consuming,
    especially on large datasets (like the whole planet). Defaults to
    :py:const:`DEFAULT_STEP_LIMIT`. Only set to ``None`` on small, contained graphs.
    """
    queue: List[_AStarQueueItem] = []
    came_from: Dict[_NodeAndBefore, _NodeAndBefore] = {}
    known_costs: Dict[_NodeAndBefore, float] = {}
    end_position = g.get_node(end).position
    steps = 0

    # Push the start element onto the queue
    queue.append(
        _AStarQueueItem(
            node_id=start,
            cost=0.0,
            score=distance(end_position, g.get_node(start).position),
        )
    )
    known_costs[_NodeAndBefore(start, None)] = 0.0

    while queue:
        item = heappop(queue)
        item_key = _NodeAndBefore(item.node_id, item.external_id_before)

        if item.node_id == end:
            return _reconstruct_path_without_turn_around(came_from, item_key)

        # Contrary to the Wikipedia definition, in this implementation there can be
        # many queue elements representing the same node. For example, a way to node X
        # could first be encountered with a cost of 10, but further down the line another
        # way to node X with cost of 5 could be found.
        # Ignore re-expanding nodes if a cheaper way was found earlier
        if item.cost > known_costs.get(item_key, inf):
            continue

        steps += 1
        if step_limit is not None and steps > step_limit:
            raise StepLimitExceeded()

        item_external_id = g.get_node(item.node_id).external_id

        for neighbor_id, cost in g.get_edges(item.node_id):
            neighbor = g.get_node(neighbor_id)

            # Disallow in-place turnarounds (A-B-A)
            if neighbor.external_id == item_key.external_id_before:
                continue

            neighbor_cost = item.cost + cost
            neighbor_key = _NodeAndBefore(neighbor_id, item_external_id)

            if neighbor_cost < known_costs.get(neighbor_key, inf):
                came_from[neighbor_key] = item_key
                known_costs[neighbor_key] = neighbor_cost
                neighbor_score = neighbor_cost + distance(end_position, neighbor.position)
                heappush(
                    queue,
                    _AStarQueueItem(
                        neighbor_id,
                        neighbor_cost,
                        neighbor_score,
                        item_external_id,
                    ),
                )

    return []


def _reconstruct_path(came_from: Mapping[int, int], last: int) -> List[int]:
    path = [last]
    nd: Optional[int] = last
    while (nd := came_from.get(nd)) is not None:
        path.append(nd)
    path.reverse()
    return path


def _reconstruct_path_without_turn_around(
    came_from: Mapping[_NodeAndBefore, _NodeAndBefore],
    last: _NodeAndBefore,
) -> List[int]:
    path = [last.node_id]
    nd: Optional[_NodeAndBefore] = last
    while (nd := came_from.get(nd)) is not None:
        path.append(nd.node_id)
    path.reverse()
    return path

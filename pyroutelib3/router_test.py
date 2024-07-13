from dataclasses import dataclass
from typing import Dict, Iterable
from unittest import TestCase

from .distance import euclidean_distance
from .protocols import GraphLike, Position
from .router import find_route, find_route_without_turn_around


@dataclass
class Node:
    id: int
    position: Position
    external_id: int = -1

    def __post_init__(self) -> None:
        if self.external_id < 0:
            self.external_id = self.id


@dataclass
class Graph(GraphLike[Node]):
    nodes: Dict[int, Node]
    edges: Dict[int, Dict[int, float]]

    def get_node(self, id: int) -> Node:
        return self.nodes[id]

    def get_edges(self, id: int) -> Iterable[tuple[int, float]]:
        return self.edges[id].items()


class TestFindRoute(TestCase):
    def test_simple(self) -> None:
        #  (20)  (20)  (20)
        # 1─────2─────3─────4
        #       └─────5─────┘
        #        (10)   (10)
        g = Graph(
            nodes={
                1: Node(1, (1, 1)),
                2: Node(2, (2, 1)),
                3: Node(3, (3, 1)),
                4: Node(4, (4, 1)),
                5: Node(5, (3, 0)),
            },
            edges={
                1: {2: 20},
                2: {1: 20, 3: 20, 5: 10},
                3: {2: 20, 4: 20},
                4: {3: 20, 5: 10},
                5: {2: 10, 4: 10},
            },
        )

        self.assertListEqual(
            find_route(g, 1, 4, distance=euclidean_distance),
            [1, 2, 5, 4],
        )

    def test_shortest_not_optimal(self) -> None:
        #     50    10
        #  7─────8─────9
        #  │     │     │
        #  │40   │30   │10
        #  │ 20  │ 40  │
        #  4─────5─────6
        #  │     │     │
        #  │60   │50   │10
        #  │ 10  │ 20  │
        #  1─────2─────3
        g = Graph(
            nodes={
                1: Node(1, (0, 0)),
                2: Node(2, (1, 0)),
                3: Node(3, (2, 0)),
                4: Node(4, (0, 1)),
                5: Node(5, (1, 1)),
                6: Node(6, (2, 1)),
                7: Node(7, (0, 2)),
                8: Node(8, (1, 2)),
                9: Node(9, (2, 2)),
            },
            edges={
                1: {2: 10, 4: 60},
                2: {1: 10, 3: 20, 5: 50},
                3: {2: 20, 6: 10},
                4: {1: 60, 5: 20, 7: 40},
                5: {2: 50, 4: 20, 6: 40, 8: 30},
                6: {3: 10, 5: 40, 9: 10},
                7: {4: 40, 8: 50},
                8: {5: 30, 7: 50, 9: 10},
                9: {6: 10, 8: 10},
            },
        )

        self.assertListEqual(
            find_route(g, 1, 8, distance=euclidean_distance),
            [1, 2, 3, 6, 9, 8],
        )


class TestFindRouteWithoutTurnAround(TestCase):
    def test(self) -> None:
        # 1
        # │
        # │10
        # │ 10
        # 2─────4
        # │     │
        # │10   │100
        # │ 10  │
        # 3─────5
        # mandatory 1-2-4
        g = Graph(
            nodes={
                1: Node(1, (0, 2)),
                2: Node(2, (0, 1)),
                20: Node(20, (0, 1), external_id=2),
                3: Node(3, (0, 0)),
                4: Node(4, (1, 1)),
                5: Node(5, (1, 0)),
            },
            edges={
                1: {20: 10},
                2: {1: 10, 3: 10, 4: 10},
                20: {4: 10},
                3: {2: 10, 5: 10},
                4: {2: 10, 5: 100},
                5: {3: 10, 4: 100},
            },
        )

        self.assertListEqual(
            find_route(g, 1, 3, distance=euclidean_distance),
            [1, 20, 4, 2, 3],
        )

        self.assertListEqual(
            find_route_without_turn_around(g, 1, 3, distance=euclidean_distance),
            [1, 20, 4, 5, 3],
        )
